from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..configuration import settings
from ..db import get_db
from ..menu_query import menu_ordered
from ..models import (
    CoinTransaction,
    MenuCategory,
    MenuItem,
    Referral,
    Order,
    OrderStatus,
    Reward,
    User,
)
from ..schemas import (
    CoinTransactionOut,
    FeedbackIn,
    FeedbackResult,
    InvitedFriend,
    ReferralSummary,
    MenuCategoryOut,
    MenuItemOut,
    OrderCreate,
    OrderOut,
    ProfileUpdate,
    RewardOut,
    UserOut,
)
from ..security import get_current_user, get_verified_member
from ..services import (
    agorot_per_coin,
    MAX_REDEEM_FRACTION,
    create_order,
    expire_coins,
    feedback_window_open,
    get_or_create_referral_code,
    submit_feedback,
    max_redeemable_coins,
    redeem_reward,
)

router = APIRouter(prefix="/api", tags=["members"])


@router.get("/menu", response_model=list[MenuItemOut])
async def list_menu(db: AsyncSession = Depends(get_db)) -> list[MenuItem]:
    """Public menu — no auth, so the storefront works before sign-in."""
    result = await db.execute(
        menu_ordered().where(MenuItem.is_available.is_(True))
    )
    return list(result.scalars().all())


@router.get("/categories", response_model=list[MenuCategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[MenuCategory]:
    """Group order for rendering the menu; public, like the menu itself."""
    rows = await db.execute(
        select(MenuCategory).order_by(MenuCategory.sort_order, MenuCategory.id)
    )
    return list(rows.scalars().all())


@router.get("/rewards", response_model=list[RewardOut])
async def list_rewards(db: AsyncSession = Depends(get_db)) -> list[Reward]:
    result = await db.execute(
        select(Reward)
        .where(Reward.is_active.is_(True))
        .order_by(Reward.cost_coins, Reward.id)
    )
    return list(result.scalars().all())


@router.get("/coins/rules")
async def coin_rules() -> dict:
    return {
        "coins_per_shekel": settings.loyalty.coins_per_shekel,
        "coin_expiry_days": settings.loyalty.coin_expiry_days,
        "agorot_per_coin": agorot_per_coin(),
        "max_redeem_fraction": MAX_REDEEM_FRACTION,
        "signup_bonus_coins": settings.loyalty.signup_bonus_coins,
        "earn_min_order_agorot": settings.loyalty.earn_min_order_agorot,
        "earn_percent": settings.loyalty.earn_percent,
        "feedback_window_hours": settings.loyalty.feedback_window_hours,
        "egg_price_agorot": settings.menu.egg_price_agorot,
    }


@router.patch("/me", response_model=UserOut)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.phone is not None:
        user.phone = payload.phone.strip() or None
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/orders", response_model=list[OrderOut])
async def my_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Order]:
    result = await db.execute(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(desc(Order.created_at))
        .limit(100)
    )
    return list(result.scalars().all())


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: OrderCreate,
    user: User = Depends(get_verified_member),
    db: AsyncSession = Depends(get_db),
) -> Order:
    order = await create_order(
        db,
        user,
        [(line.menu_item_id, line.quantity, line.eggs) for line in payload.items],
        payload.note,
        payload.redeem_coins,
    )
    await db.commit()
    await db.refresh(order)
    return order


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Order:
    order = await db.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_my_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Order:
    """Members may cancel only while the kitchen hasn't started."""
    from ..services import advance_order_status

    order = await db.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status is not OrderStatus.pending:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Order can no longer be cancelled — please call the restaurant",
        )
    await advance_order_status(db, order, OrderStatus.cancelled, actor_id=user.id)
    await db.commit()
    await db.refresh(order)
    return order


@router.post("/orders/{order_id}/feedback", response_model=FeedbackResult)
async def submit_order_feedback(
    order_id: int,
    payload: FeedbackIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResult:
    """Rate a collected order, which releases the coins held for it."""
    order = await db.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    in_time = feedback_window_open(order)
    granted = await submit_feedback(db, order, user, payload.food, payload.service)
    await db.commit()
    await db.refresh(user)
    return FeedbackResult(
        ok=True, coins_granted=granted, balance=user.coin_balance, in_time=in_time
    )


@router.get("/referrals", response_model=ReferralSummary)
async def my_referrals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReferralSummary:
    """This member's invite link and who has joined through it."""
    code = await get_or_create_referral_code(db, user)
    await db.commit()

    rows = (
        await db.execute(
            select(Referral, User)
            .join(User, User.id == Referral.invitee_id)
            .where(Referral.inviter_id == user.id)
            .order_by(desc(Referral.created_at))
        )
    ).all()

    friends = [
        InvitedFriend(
            # First name only: the inviter does not need their friend's email.
            name=(invitee.full_name or invitee.email).split()[0],
            joined_at=referral.created_at,
            completed=referral.completed_at is not None,
            coins_earned=referral.inviter_coins,
        )
        for referral, invitee in rows
    ]
    completed = sum(1 for f in friends if f.completed)
    loyalty = settings.loyalty

    return ReferralSummary(
        code=code,
        link=f"{settings.frontend_url}/?ref={code}",
        coins_per_friend=loyalty.referral_inviter_coins,
        friend_bonus_coins=loyalty.referral_invitee_coins,
        max_friends=loyalty.referral_max_friends,
        completed_count=completed,
        pending_count=len(friends) - completed,
        coins_earned=sum(f.coins_earned for f in friends),
        slots_left=max(0, loyalty.referral_max_friends - completed),
        friends=friends,
    )


@router.get("/coins/transactions", response_model=list[CoinTransactionOut])
async def my_coin_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CoinTransaction]:
    # Reading the history is a natural moment to retire lapsed coins.
    if await expire_coins(db, user):
        await db.commit()
    result = await db.execute(
        select(CoinTransaction)
        .where(CoinTransaction.user_id == user.id)
        .order_by(desc(CoinTransaction.created_at), desc(CoinTransaction.id))
        .limit(200)
    )
    return list(result.scalars().all())


@router.get("/coins/redeemable")
async def redeemable_preview(
    subtotal_agorot: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await expire_coins(db, user):
        await db.commit()
    allowed = max_redeemable_coins(subtotal_agorot, user.coin_balance)
    return {
        "balance": user.coin_balance,
        "max_coins": allowed,
        "max_discount_agorot": allowed * agorot_per_coin(),
    }


@router.post("/rewards/{reward_id}/redeem")
async def redeem(
    reward_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    reward = await db.get(Reward, reward_id)
    if reward is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reward not found")
    tx = await redeem_reward(db, user, reward)
    await db.commit()
    return {
        "ok": True,
        "reward": reward.name_he,
        "coins_spent": reward.cost_coins,
        "balance": tx.balance_after,
        "voucher_code": f"RW-{reward.id}-{tx.id}",
    }
