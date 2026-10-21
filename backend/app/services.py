"""Domain logic: the Poet Coin ledger, order pricing and activity logging."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .configuration import settings
from .models import (
    ActivityLog,
    CoinTransaction,
    CoinTxKind,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
    PaymentStatus,
    User,
)

# Redemption rate: how much one Poet Coin is worth when spent.
AGOROT_PER_COIN = 10  # 100 coins = 10.00 ILS
# Coins may not cover the whole bill; keep some cash in every order.
MAX_REDEEM_FRACTION = 0.5


def coins_for_amount(total_agorot: int) -> int:
    """Coins earned for a paid order: COINS_PER_SHEKEL per whole shekel."""
    return (total_agorot // 100) * settings.loyalty.coins_per_shekel


def new_order_number() -> str:
    """Human-friendly, non-sequential order reference."""
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    return f"PH-{stamp}-{secrets.choice(range(10000)):04d}"


async def log_activity(
    db: AsyncSession,
    action: str,
    *,
    user_id: int | None = None,
    actor_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        ActivityLog(
            user_id=user_id,
            actor_id=actor_id,
            action=action,
            details=details or {},
            ip_address=ip_address,
        )
    )


async def record_coins(
    db: AsyncSession,
    user: User,
    amount: int,
    kind: CoinTxKind,
    *,
    reason: str = "",
    order_id: int | None = None,
    reward_id: int | None = None,
    created_by_id: int | None = None,
) -> CoinTransaction:
    """Move coins and append a ledger row. `amount` is signed."""
    if amount == 0:
        raise ValueError("Coin transaction amount must be non-zero")

    new_balance = user.coin_balance + amount
    if new_balance < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Insufficient Poet Coin balance"
        )

    user.coin_balance = new_balance
    if amount > 0 and kind is not CoinTxKind.refund:
        user.lifetime_coins_earned += amount

    tx = CoinTransaction(
        user_id=user.id,
        order_id=order_id,
        reward_id=reward_id,
        amount=amount,
        kind=kind,
        balance_after=new_balance,
        reason=reason,
        created_by_id=created_by_id,
    )
    db.add(tx)
    return tx


def max_redeemable_coins(subtotal_agorot: int, balance: int) -> int:
    """Cap redemption at half the bill and at what the member actually holds."""
    cap_agorot = int(subtotal_agorot * MAX_REDEEM_FRACTION)
    return max(0, min(balance, cap_agorot // AGOROT_PER_COIN))


async def create_order(
    db: AsyncSession,
    user: User,
    lines: list[tuple[int, int]],
    note: str,
    redeem_coins: int,
) -> Order:
    """Build an order from (menu_item_id, quantity) pairs."""
    wanted_ids = {mid for mid, _ in lines}
    rows = (
        await db.execute(select(MenuItem).where(MenuItem.id.in_(wanted_ids)))
    ).scalars().all()
    by_id = {m.id: m for m in rows}

    missing = wanted_ids - by_id.keys()
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown menu item(s): {sorted(missing)}",
        )
    unavailable = [by_id[i].name_he for i in wanted_ids if not by_id[i].is_available]
    if unavailable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Item(s) currently unavailable: {', '.join(unavailable)}",
        )

    # Merge duplicate lines for the same item.
    quantities: dict[int, int] = {}
    for mid, qty in lines:
        quantities[mid] = quantities.get(mid, 0) + qty

    order_items: list[OrderItem] = []
    subtotal = 0
    for mid, qty in quantities.items():
        item = by_id[mid]
        line_total = item.price_agorot * qty
        subtotal += line_total
        order_items.append(
            OrderItem(
                menu_item_id=item.id,
                name_snapshot=item.name_he,
                unit_price_agorot=item.price_agorot,
                quantity=qty,
                line_total_agorot=line_total,
            )
        )

    allowed = max_redeemable_coins(subtotal, user.coin_balance)
    if redeem_coins > allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Can redeem at most {allowed} coins on this order",
        )

    discount = redeem_coins * AGOROT_PER_COIN
    total = subtotal - discount

    order = Order(
        order_number=new_order_number(),
        user_id=user.id,
        status=OrderStatus.pending,
        payment_status=PaymentStatus.unpaid,
        subtotal_agorot=subtotal,
        discount_agorot=discount,
        total_agorot=total,
        coins_spent=redeem_coins,
        note=note,
        items=order_items,
    )
    db.add(order)
    await db.flush()  # assign order.id before writing the ledger row

    if redeem_coins:
        await record_coins(
            db,
            user,
            -redeem_coins,
            CoinTxKind.redeem,
            reason=f"מימוש בהזמנה {order.order_number}",
            order_id=order.id,
        )

    await log_activity(
        db,
        "order.created",
        user_id=user.id,
        details={
            "order_number": order.order_number,
            "total_agorot": total,
            "coins_spent": redeem_coins,
        },
    )
    return order


async def mark_order_paid(db: AsyncSession, order: Order) -> None:
    """Stubbed payment capture. Swap for a real PSP webhook later."""
    if order.payment_status is PaymentStatus.paid:
        return
    order.payment_status = PaymentStatus.paid
    order.payment_reference = f"MOCK-{secrets.token_hex(6).upper()}"
    await log_activity(
        db,
        "order.paid",
        user_id=order.user_id,
        details={"order_number": order.order_number, "total_agorot": order.total_agorot},
    )


async def advance_order_status(
    db: AsyncSession,
    order: Order,
    new_status: OrderStatus,
    *,
    actor_id: int | None = None,
) -> Order:
    """Apply a status change, awarding or refunding coins at the edges."""
    if order.status is new_status:
        return order
    if order.status in (OrderStatus.collected, OrderStatus.cancelled):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Order is already {order.status.value} and cannot change",
        )

    previous = order.status
    order.status = new_status
    user = await db.get(User, order.user_id)

    if new_status is OrderStatus.collected:
        order.collected_at = datetime.now(timezone.utc)
        await mark_order_paid(db, order)
        if not order.coins_awarded:
            earned = coins_for_amount(order.total_agorot)
            order.coins_earned = earned
            order.coins_awarded = True
            if earned and user is not None:
                await record_coins(
                    db,
                    user,
                    earned,
                    CoinTxKind.earn,
                    reason=f"הזמנה {order.order_number}",
                    order_id=order.id,
                )

    elif new_status is OrderStatus.cancelled:
        # Give back any coins the member spent on this order.
        if order.coins_spent and user is not None:
            await record_coins(
                db,
                user,
                order.coins_spent,
                CoinTxKind.refund,
                reason=f"ביטול הזמנה {order.order_number}",
                order_id=order.id,
            )

    await log_activity(
        db,
        "order.status_changed",
        user_id=order.user_id,
        actor_id=actor_id,
        details={
            "order_number": order.order_number,
            "from": previous.value,
            "to": new_status.value,
        },
    )
    return order


async def redeem_reward(
    db: AsyncSession, user: User, reward
) -> CoinTransaction:
    if not reward.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reward is not active")
    if user.coin_balance < reward.cost_coins:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Insufficient Poet Coin balance"
        )
    tx = await record_coins(
        db,
        user,
        -reward.cost_coins,
        CoinTxKind.redeem,
        reason=f"מימוש הטבה: {reward.name_he}",
        reward_id=reward.id,
    )
    await log_activity(
        db,
        "reward.redeemed",
        user_id=user.id,
        details={"reward": reward.name_he, "cost_coins": reward.cost_coins},
    )
    return tx
