from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..menu_query import menu_ordered
from ..models import (
    CoinTransaction,
    MenuCategory,
    MenuItem,
    Order,
    OrderStatus,
    Reward,
    User,
)
from ..schemas import (
    CoinTransactionOut,
    MenuCategoryOut,
    MenuItemOut,
    OrderCreate,
    OrderOut,
    ProfileUpdate,
    RewardOut,
    UserOut,
)
from ..security import get_current_user
from ..services import (
    AGOROT_PER_COIN,
    MAX_REDEEM_FRACTION,
    create_order,
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
    from ..configuration import settings

    return {
        "coins_per_shekel": settings.loyalty.coins_per_shekel,
        "agorot_per_coin": AGOROT_PER_COIN,
        "max_redeem_fraction": MAX_REDEEM_FRACTION,
        "signup_bonus_coins": settings.loyalty.signup_bonus_coins,
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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Order:
    order = await create_order(
        db,
        user,
        [(line.menu_item_id, line.quantity) for line in payload.items],
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


@router.get("/coins/transactions", response_model=list[CoinTransactionOut])
async def my_coin_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CoinTransaction]:
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
) -> dict:
    allowed = max_redeemable_coins(subtotal_agorot, user.coin_balance)
    return {
        "balance": user.coin_balance,
        "max_coins": allowed,
        "max_discount_agorot": allowed * AGOROT_PER_COIN,
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
