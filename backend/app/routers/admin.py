import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import Select, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..configuration import settings
from ..db import get_db
from ..phone import display_phone, normalise_phone_or_400
from ..menu_query import menu_ordered
from ..models import (
    ActivityLog,
    MenuCategory,
    CoinTransaction,
    CoinTxKind,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
    PaymentStatus,
    Reward,
    User,
    UserRole,
)
from ..schemas import (
    ActivityLogOut,
    AdminOrderOut,
    MenuCategoryOut,
    AdminStats,
    AdminUserRow,
    CoinAdjust,
    CoinTransactionOut,
    MenuItemIn,
    MenuItemOut,
    MenuItemPatch,
    OrderOut,
    ReorderRequest,
    Paginated,
    RewardOut,
    UserOut,
)
from ..security import get_current_admin
from ..services import advance_order_status, log_activity, record_coins

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin)]
)


def _start_of_today() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _scalar(db: AsyncSession, stmt: Select) -> int:
    return (await db.execute(stmt)).scalar() or 0


@router.get("/stats", response_model=AdminStats)
async def stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    today = _start_of_today()
    revenue_filter = Order.payment_status == PaymentStatus.paid

    return AdminStats(
        total_members=await _scalar(
            db, select(func.count(User.id)).where(User.role == UserRole.member)
        ),
        total_orders=await _scalar(db, select(func.count(Order.id))),
        orders_today=await _scalar(
            db, select(func.count(Order.id)).where(Order.created_at >= today)
        ),
        revenue_agorot=await _scalar(
            db, select(func.sum(Order.total_agorot)).where(revenue_filter)
        ),
        revenue_today_agorot=await _scalar(
            db,
            select(func.sum(Order.total_agorot)).where(
                revenue_filter, Order.created_at >= today
            ),
        ),
        coins_outstanding=await _scalar(db, select(func.sum(User.coin_balance))),
        coins_issued=await _scalar(
            db,
            select(func.sum(CoinTransaction.amount)).where(CoinTransaction.amount > 0),
        ),
        coins_redeemed=abs(
            await _scalar(
                db,
                select(func.sum(CoinTransaction.amount)).where(
                    CoinTransaction.amount < 0
                ),
            )
        ),
        active_orders=await _scalar(
            db,
            select(func.count(Order.id)).where(
                Order.status.in_(
                    [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready]
                )
            ),
        ),
    )


@router.get("/users", response_model=Paginated[AdminUserRow])
async def list_users(
    q: str | None = None,
    role: UserRole | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Paginated[AdminUserRow]:
    # Per-user order aggregates, counting only money actually collected.
    agg = (
        select(
            Order.user_id.label("uid"),
            func.count(Order.id).label("order_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Order.payment_status == PaymentStatus.paid, Order.total_agorot),
                        else_=0,
                    )
                ),
                0,
            ).label("total_spent"),
        )
        .group_by(Order.user_id)
        .subquery()
    )

    stmt = select(User, agg.c.order_count, agg.c.total_spent).outerjoin(
        agg, agg.c.uid == User.id
    )
    count_stmt = select(func.count(User.id))

    if q:
        pattern = f"%{q.strip().lower()}%"
        cond = func.lower(User.email).like(pattern) | func.lower(User.full_name).like(
            pattern
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if role is not None:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = await db.execute(
        stmt.order_by(desc(User.created_at)).offset((page - 1) * page_size).limit(page_size)
    )

    items: list[AdminUserRow] = []
    for user, order_count, total_spent in rows.all():
        row = AdminUserRow.model_validate(user)
        row.order_count = order_count or 0
        row.total_spent_agorot = total_spent or 0
        items.append(row)

    return Paginated[AdminUserRow](
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/users/{user_id}")
async def user_detail(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Everything about one member: profile, orders, ledger, activity."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    orders = (
        await db.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(desc(Order.created_at))
            .limit(100)
        )
    ).scalars().all()
    coins = (
        await db.execute(
            select(CoinTransaction)
            .where(CoinTransaction.user_id == user_id)
            .order_by(desc(CoinTransaction.created_at), desc(CoinTransaction.id))
            .limit(100)
        )
    ).scalars().all()
    activity = (
        await db.execute(
            select(ActivityLog)
            .where(ActivityLog.user_id == user_id)
            .order_by(desc(ActivityLog.created_at))
            .limit(100)
        )
    ).scalars().all()

    return {
        "user": UserOut.model_validate(user),
        "orders": [OrderOut.model_validate(o) for o in orders],
        "coin_transactions": [CoinTransactionOut.model_validate(c) for c in coins],
        "activity": [ActivityLogOut.model_validate(a) for a in activity],
    }


@router.post("/users/{user_id}/coins", response_model=UserOut)
async def adjust_coins(
    user_id: int,
    payload: CoinAdjust,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Manually credit or debit a member's coins, with an audit trail."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if payload.amount == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Amount must be non-zero")

    await record_coins(
        db,
        user,
        payload.amount,
        CoinTxKind.admin_adjust,
        reason=payload.reason,
        created_by_id=admin.id,
    )
    await log_activity(
        db,
        "admin.coins_adjusted",
        user_id=user.id,
        actor_id=admin.id,
        details={"amount": payload.amount, "reason": payload.reason},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/verify-phone", response_model=UserOut)
async def verify_user_phone(
    user_id: int,
    payload: dict,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Set and confirm a member's phone without sending a code.

    For support cases — a member who changed number, or cannot receive SMS —
    and for bootstrapping before a provider is configured. Every use is
    written to the activity log, so a manually confirmed number is never
    indistinguishable from one that passed a real code.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    raw_phone = (payload.get("phone") or "").strip()
    if raw_phone:
        phone = normalise_phone_or_400(raw_phone)
        clash = (
            await db.execute(
                select(User).where(User.phone == phone, User.id != user.id)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"מספר הטלפון משויך לחשבון {clash.email}",
            )
        user.phone = phone
    elif not user.phone:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "למשתמש אין מספר טלפון — ציינו מספר",
        )

    user.phone_verified_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        "phone.verified",
        user_id=user.id,
        actor_id=admin.id,
        details={"via": "admin", "phone_set": bool(raw_phone)},
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.from_user(user)


@router.post("/users/{user_id}/toggle-active", response_model=UserOut)
async def toggle_active(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot disable your own account"
        )

    user.is_active = not user.is_active
    await log_activity(
        db,
        "admin.user_toggled",
        user_id=user.id,
        actor_id=admin.id,
        details={"is_active": user.is_active},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/orders", response_model=Paginated[AdminOrderOut])
async def list_orders(
    status_filter: OrderStatus | None = Query(None, alias="status"),
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Paginated[AdminOrderOut]:
    # Join the customer so the kitchen sees who each order belongs to; one
    # query rather than a lookup per row.
    stmt = select(Order, User).join(User, User.id == Order.user_id)
    count_stmt = select(func.count(Order.id)).join(User, User.id == Order.user_id)

    if status_filter is not None:
        stmt = stmt.where(Order.status == status_filter)
        count_stmt = count_stmt.where(Order.status == status_filter)
    if q:
        pattern = f"%{q.strip().lower()}%"
        cond = (
            func.lower(User.full_name).like(pattern)
            | func.lower(User.email).like(pattern)
            | func.lower(Order.order_number).like(pattern)
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = await db.execute(
        stmt.order_by(desc(Order.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = [
        AdminOrderOut(
            **OrderOut.model_validate(order).model_dump(),
            customer_id=customer.id,
            # Fall back to the email when a Google account has no name set.
            customer_name=customer.full_name or customer.email,
            customer_email=customer.email,
            customer_phone=display_phone(customer.phone) if customer.phone else None,
            customer_phone_verified=customer.phone_verified_at is not None,
        )
        for order, customer in rows.all()
    ]

    return Paginated[AdminOrderOut](
        items=items, total=total, page=page, page_size=page_size
    )


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
async def set_order_status(
    order_id: int,
    payload: dict,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Order:
    order = await db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    try:
        new_status = OrderStatus(payload["status"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status") from None

    await advance_order_status(db, order, new_status, actor_id=admin.id)
    await db.commit()
    await db.refresh(order)
    return order


@router.get("/activity", response_model=Paginated[ActivityLogOut])
async def list_activity(
    action: str | None = None,
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Paginated[ActivityLogOut]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(ActivityLog).where(ActivityLog.created_at >= since)
    count_stmt = select(func.count(ActivityLog.id)).where(ActivityLog.created_at >= since)
    if action:
        stmt = stmt.where(ActivityLog.action == action)
        count_stmt = count_stmt.where(ActivityLog.action == action)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = await db.execute(
        stmt.order_by(desc(ActivityLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Paginated[ActivityLogOut](
        items=[ActivityLogOut.model_validate(a) for a in rows.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------- Menu management ----------


@router.get("/menu", response_model=list[MenuItemOut])
async def admin_list_menu(db: AsyncSession = Depends(get_db)) -> list[MenuItem]:
    """Unlike the public menu, this includes unavailable items."""
    rows = await db.execute(
        menu_ordered()
    )
    return list(rows.scalars().all())


@router.post("/menu", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED)
async def create_menu_item(
    payload: MenuItemIn, db: AsyncSession = Depends(get_db)
) -> MenuItem:
    item = MenuItem(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/menu/{item_id}", response_model=MenuItemOut)
async def update_menu_item(
    item_id: int, payload: MenuItemPatch, db: AsyncSession = Depends(get_db)
) -> MenuItem:
    item = await db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return item


# Uploaded item photos live here and are served at /media.
MEDIA_ROOT = settings.media_dir / "menu"
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _sniff_image(data: bytes) -> str | None:
    """Identify an image by its magic bytes (stdlib imghdr is gone in 3.13).

    Returns the file extension to store under, or None if unrecognised.
    """
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


@router.post("/menu/{item_id}/image", response_model=MenuItemOut)
async def upload_menu_image(
    item_id: int,
    admin: User = Depends(get_current_admin),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> MenuItem:
    """Attach a photo to a menu item, replacing any previous one."""
    item = await db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")

    payload = await file.read(MAX_IMAGE_BYTES + 1)
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    if len(payload) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image must be 4MB or smaller"
        )

    # Trust the bytes, not the filename or the client-supplied content type.
    suffix = _sniff_image(payload)
    if suffix is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Unsupported image format — use JPEG, PNG, GIF or WebP",
        )

    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"{item_id}-{secrets.token_hex(8)}{suffix}"
    (MEDIA_ROOT / filename).write_bytes(payload)

    previous = item.image_url
    item.image_url = f"/media/menu/{filename}"

    await log_activity(
        db,
        "admin.menu_image_uploaded",
        actor_id=admin.id,
        details={"item": item.name_he, "file": filename},
    )
    await db.commit()
    await db.refresh(item)

    # Drop the old file only once the new path is safely committed.
    if previous:
        _remove_media(previous)
    return item


@router.delete("/menu/{item_id}/image", response_model=MenuItemOut)
async def delete_menu_image(
    item_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> MenuItem:
    item = await db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")

    previous = item.image_url
    item.image_url = None
    await log_activity(
        db, "admin.menu_image_removed", actor_id=admin.id, details={"item": item.name_he}
    )
    await db.commit()
    await db.refresh(item)
    if previous:
        _remove_media(previous)
    return item


def _remove_media(url: str) -> None:
    """Delete a previously uploaded file, ignoring anything outside MEDIA_ROOT."""
    try:
        candidate = (MEDIA_ROOT / Path(url).name).resolve()
        if candidate.is_relative_to(MEDIA_ROOT.resolve()) and candidate.is_file():
            candidate.unlink()
    except OSError:
        # A missing or unreadable file must not fail the request.
        pass


@router.delete("/menu/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu_item(
    item_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove an item outright when it was never ordered, otherwise retire it.

    Order lines keep a name/price snapshot, but deleting a row that history
    points at would blank out the link, so those are hidden instead.
    """
    item = await db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")

    ordered = (
        await db.execute(
            select(func.count(OrderItem.id)).where(OrderItem.menu_item_id == item_id)
        )
    ).scalar() or 0

    image = item.image_url
    if ordered:
        item.is_available = False
        action = "admin.menu_item_retired"
    else:
        await db.delete(item)
        action = "admin.menu_item_deleted"

    await log_activity(
        db,
        action,
        actor_id=admin.id,
        details={"item": item.name_he, "past_orders": ordered},
    )
    await db.commit()
    if image and not ordered:
        _remove_media(image)


@router.get("/categories", response_model=list[MenuCategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[MenuCategory]:
    rows = await db.execute(
        select(MenuCategory).order_by(MenuCategory.sort_order, MenuCategory.id)
    )
    return list(rows.scalars().all())


@router.post("/categories/reorder", response_model=list[MenuCategoryOut])
async def reorder_categories(
    payload: ReorderRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[MenuCategory]:
    """Rewrite category positions to match the order of the ids given."""
    rows = (
        await db.execute(select(MenuCategory).where(MenuCategory.id.in_(payload.ids)))
    ).scalars().all()
    by_id = {c.id: c for c in rows}

    missing = set(payload.ids) - by_id.keys()
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown category id(s): {sorted(missing)}"
        )

    for position, category_id in enumerate(payload.ids):
        by_id[category_id].sort_order = position

    await log_activity(
        db,
        "admin.categories_reordered",
        actor_id=admin.id,
        details={"order": [by_id[i].key for i in payload.ids]},
    )
    await db.commit()

    result = await db.execute(
        select(MenuCategory).order_by(MenuCategory.sort_order, MenuCategory.id)
    )
    return list(result.scalars().all())


@router.post("/menu/reorder", response_model=list[MenuItemOut])
async def reorder_menu_items(
    payload: ReorderRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[MenuItem]:
    """Rewrite item positions within their category to match the ids given."""
    rows = (
        await db.execute(select(MenuItem).where(MenuItem.id.in_(payload.ids)))
    ).scalars().all()
    by_id = {m.id: m for m in rows}

    missing = set(payload.ids) - by_id.keys()
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown menu item id(s): {sorted(missing)}"
        )
    categories = {by_id[i].category for i in payload.ids}
    if len(categories) > 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Reorder one category at a time — ids span several categories",
        )

    for position, item_id in enumerate(payload.ids):
        by_id[item_id].sort_order = position

    await log_activity(
        db,
        "admin.menu_reordered",
        actor_id=admin.id,
        details={"category": categories.pop(), "count": len(payload.ids)},
    )
    await db.commit()

    result = await db.execute(menu_ordered())
    return list(result.scalars().all())


@router.get("/rewards", response_model=list[RewardOut])
async def admin_list_rewards(db: AsyncSession = Depends(get_db)) -> list[Reward]:
    rows = await db.execute(select(Reward).order_by(Reward.cost_coins))
    return list(rows.scalars().all())
