"""Domain logic: the Poet Coin ledger, order pricing and activity logging."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

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
# Coins may not cover the whole bill; keep some cash in every order.
MAX_REDEEM_FRACTION = 0.5


def agorot_per_coin() -> int:
    """What one coin is worth when redeemed. Read live so config changes apply."""
    return settings.loyalty.agorot_per_coin


def coins_for_amount(total_agorot: int) -> int:
    """Coins earned for an order, based on the amount actually paid.

    A percentage of the paid total, and nothing at all below the minimum —
    so coins cannot partly regenerate themselves through redemption.
    """
    loyalty = settings.loyalty
    if total_agorot < loyalty.earn_min_order_agorot:
        return 0
    return int(total_agorot * loyalty.earn_percent / 100 // 100)


def feedback_deadline(collected_at: datetime) -> datetime:
    """Last moment feedback can still release an order's pending coins."""
    return collected_at + timedelta(hours=settings.loyalty.feedback_window_hours)


def feedback_window_open(order: Order, now: datetime | None = None) -> bool:
    if order.collected_at is None:
        return False
    moment = now or datetime.now(timezone.utc)
    collected = order.collected_at
    if collected.tzinfo is None:  # SQLite returns naive datetimes
        collected = collected.replace(tzinfo=timezone.utc)
    return moment <= feedback_deadline(collected)


# Digits only, grouped in fours: 1234-5678-9012-3456. Easy to read aloud
# across a counter, and it leaks nothing about volume or timing.
ORDER_NUMBER_GROUPS = 4
ORDER_NUMBER_GROUP_SIZE = 4


def new_order_number() -> str:
    """A random 16-digit reference, hyphenated into groups of four."""
    groups = [
        f"{secrets.randbelow(10 ** ORDER_NUMBER_GROUP_SIZE):0{ORDER_NUMBER_GROUP_SIZE}d}"
        for _ in range(ORDER_NUMBER_GROUPS)
    ]
    return "-".join(groups)


async def allocate_order_number(db: AsyncSession, attempts: int = 5) -> str:
    """A reference not already taken.

    A collision across 10^16 values is vanishingly unlikely, but the column is
    unique, so retrying here keeps a freak clash from failing a real order.
    """
    for _ in range(attempts):
        candidate = new_order_number()
        taken = (
            await db.execute(
                select(Order.id).where(Order.order_number == candidate).limit(1)
            )
        ).scalar_one_or_none()
        if taken is None:
            return candidate
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Could not allocate an order number, please try again",
    )


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


def coin_expiry_for(now: datetime | None = None) -> datetime | None:
    """When coins earned right now would lapse, or None if expiry is off."""
    days = settings.loyalty.coin_expiry_days
    if days <= 0:
        return None
    return (now or datetime.now(timezone.utc)) + timedelta(days=days)


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def _open_credits(db: AsyncSession, user_id: int) -> list[CoinTransaction]:
    """Unconsumed credit rows, oldest first, so the soonest to lapse goes first."""
    rows = (
        await db.execute(
            select(CoinTransaction)
            .where(
                CoinTransaction.user_id == user_id,
                CoinTransaction.amount > 0,
                CoinTransaction.consumed < CoinTransaction.amount,
            )
            .order_by(CoinTransaction.created_at, CoinTransaction.id)
        )
    ).scalars().all()
    return list(rows)


async def _consume_credits(db: AsyncSession, user_id: int, amount: int) -> None:
    """Mark `amount` coins as used against the oldest open credits."""
    remaining = amount
    for credit in await _open_credits(db, user_id):
        if remaining <= 0:
            break
        available = credit.amount - credit.consumed
        take = min(available, remaining)
        credit.consumed += take
        remaining -= take


async def expire_coins(
    db: AsyncSession, user: User, now: datetime | None = None
) -> int:
    """Lapse any credits past their expiry, writing one ledger row per batch.

    Called lazily whenever a balance is read or spent, so no scheduled job is
    needed — which matters on hosts that do not offer one.
    """
    moment = now or datetime.now(timezone.utc)
    lapsed = 0
    for credit in await _open_credits(db, user.id):
        if credit.expires_at is None:
            continue
        if _aware(credit.expires_at) <= moment:
            outstanding = credit.amount - credit.consumed
            credit.consumed = credit.amount
            lapsed += outstanding

    if lapsed:
        await record_coins(
            db,
            user,
            -lapsed,
            CoinTxKind.expired,
            reason="פקיעת תוקף מטבעות",
            skip_expiry_check=True,
        )
        await log_activity(
            db, "coins.expired", user_id=user.id, details={"amount": lapsed}
        )
    return lapsed


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
    skip_expiry_check: bool = False,
) -> CoinTransaction:
    """Move coins and append a ledger row. `amount` is signed."""
    if amount == 0:
        raise ValueError("Coin transaction amount must be non-zero")

    # Spending must not draw on coins that have already lapsed.
    if amount < 0 and not skip_expiry_check:
        await expire_coins(db, user)

    new_balance = user.coin_balance + amount
    if new_balance < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Insufficient Poet Coin balance"
        )

    user.coin_balance = new_balance
    if amount > 0 and kind is not CoinTxKind.refund:
        user.lifetime_coins_earned += amount

    # Credits carry an expiry; debits retire the oldest credits first.
    if amount < 0:
        await _consume_credits(db, user.id, -amount)

    tx = CoinTransaction(
        user_id=user.id,
        order_id=order_id,
        reward_id=reward_id,
        amount=amount,
        kind=kind,
        balance_after=new_balance,
        reason=reason,
        expires_at=coin_expiry_for() if amount > 0 else None,
        created_by_id=created_by_id,
    )
    db.add(tx)
    await db.flush()  # the row must exist before the next FIFO scan
    return tx


def max_redeemable_coins(subtotal_agorot: int, balance: int) -> int:
    """Cap redemption at half the bill and at what the member actually holds."""
    cap_agorot = int(subtotal_agorot * MAX_REDEEM_FRACTION)
    return max(0, min(balance, cap_agorot // agorot_per_coin()))


async def create_order(
    db: AsyncSession,
    user: User,
    lines: list[tuple[int, int]] | list[tuple[int, int, int]],
    note: str,
    redeem_coins: int,
) -> Order:
    """Build an order from (menu_item_id, quantity) or (id, qty, eggs) tuples."""
    # Normalise to a 3-tuple so callers may omit the egg count.
    normalised: list[tuple[int, int, int]] = [
        (line[0], line[1], line[2] if len(line) > 2 else 0) for line in lines
    ]
    lines = normalised  # type: ignore[assignment]
    wanted_ids = {mid for mid, _, _ in normalised}
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

    # Reject eggs on dishes that do not offer them.
    bad_eggs = [
        by_id[mid].name_he
        for mid, _, eggs in normalised
        if eggs and not by_id[mid].allows_egg
    ]
    if bad_eggs:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Egg cannot be added to: {', '.join(sorted(set(bad_eggs)))}",
        )

    # Merge duplicate lines, but only when the add-ons match: two plates of
    # the same hummus with different egg counts stay separate lines.
    merged: dict[tuple[int, int], int] = {}
    for mid, qty, eggs in normalised:
        merged[(mid, eggs)] = merged.get((mid, eggs), 0) + qty

    egg_price = settings.menu.egg_price_agorot
    order_items: list[OrderItem] = []
    subtotal = 0
    for (mid, eggs), qty in merged.items():
        item = by_id[mid]
        # Eggs are per plate, so they scale with the quantity.
        line_total = (item.price_agorot + eggs * egg_price) * qty
        subtotal += line_total
        order_items.append(
            OrderItem(
                menu_item_id=item.id,
                name_snapshot=item.name_he,
                unit_price_agorot=item.price_agorot,
                quantity=qty,
                eggs=eggs,
                egg_price_agorot=egg_price if eggs else 0,
                line_total_agorot=line_total,
            )
        )

    allowed = max_redeemable_coins(subtotal, user.coin_balance)
    if redeem_coins > allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Can redeem at most {allowed} coins on this order",
        )

    discount = redeem_coins * agorot_per_coin()
    total = subtotal - discount

    order = Order(
        order_number=await allocate_order_number(db),
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
        if not order.coins_awarded and not order.coins_pending:
            # Coins are held until the member rates the order; see
            # submit_feedback. Nothing is pending when the order is too small.
            order.coins_pending = coins_for_amount(order.total_agorot)

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


async def submit_feedback(
    db: AsyncSession,
    order: Order,
    user: User,
    food: int,
    service: int,
) -> int:
    """Record the member's ratings and release the order's pending coins.

    Returns the number of coins granted (0 when the order earned none or the
    window has closed). Feedback is still recorded after the deadline — it is
    useful to the restaurant either way — but the coins are forfeited.
    """
    if order.status is not OrderStatus.collected:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ניתן לדרג רק הזמנה שנאספה",
        )
    if order.feedback_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "כבר דירגתם הזמנה זו")

    order.feedback_food = food
    order.feedback_service = service
    order.feedback_at = datetime.now(timezone.utc)

    granted = 0
    in_time = feedback_window_open(order)
    if order.coins_pending and in_time:
        granted = order.coins_pending
        order.coins_earned = granted
        order.coins_awarded = True
        await record_coins(
            db,
            user,
            granted,
            CoinTxKind.earn,
            reason=f"הזמנה {order.order_number}",
            order_id=order.id,
        )
    order.coins_pending = 0

    await log_activity(
        db,
        "order.feedback_submitted",
        user_id=user.id,
        details={
            "order_number": order.order_number,
            "food": food,
            "service": service,
            "coins_granted": granted,
            "in_time": in_time,
        },
    )
    return granted


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
