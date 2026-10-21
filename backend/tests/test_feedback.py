"""Earning rules: minimum order, percentage, and the feedback gate."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.configuration import settings
from app.models import CoinTxKind, MenuItem, OrderStatus
from app.services import (
    advance_order_status,
    coins_for_amount,
    create_order,
    feedback_window_open,
    record_coins,
    submit_feedback,
)


async def _item(db, price: int) -> MenuItem:
    item = MenuItem(name_he="מנה", category="hummus", price_agorot=price)
    db.add(item)
    await db.flush()
    return item


async def _collected_order(db, member, price: int, redeem: int = 0):
    item = await _item(db, price)
    order = await create_order(db, member, [(item.id, 1)], "", redeem)
    for state in (OrderStatus.preparing, OrderStatus.ready, OrderStatus.collected):
        await advance_order_status(db, order, state)
    return order


# --- the earning formula ---------------------------------------------------


@pytest.mark.parametrize(
    "paid_agorot,expected",
    [
        (0, 0),
        (4499, 0),      # just under the ₪45 minimum
        (4500, 2),      # exactly the minimum: 5% of ₪45 = ₪2.25 -> 2
        (5000, 2),
        (8000, 4),
        (10000, 5),     # 5% of ₪100
        (20000, 10),
    ],
)
def test_coins_are_five_percent_above_the_minimum(paid_agorot, expected):
    assert coins_for_amount(paid_agorot) == expected


def test_nothing_is_earned_below_the_minimum_order():
    assert settings.loyalty.earn_min_order_agorot == 4500
    assert coins_for_amount(settings.loyalty.earn_min_order_agorot - 1) == 0
    assert coins_for_amount(settings.loyalty.earn_min_order_agorot) > 0


# --- coins are held, not granted, at collection ----------------------------


async def test_collection_holds_coins_instead_of_granting_them(db, member):
    order = await _collected_order(db, member, 10000)
    await db.commit()

    assert order.coins_pending == 5
    assert order.coins_earned == 0
    assert order.coins_awarded is False
    assert member.coin_balance == 0, "coins must wait for feedback"


async def test_feedback_releases_the_pending_coins(db, member):
    order = await _collected_order(db, member, 10000)
    await db.commit()

    granted = await submit_feedback(db, order, member, food=5, service=4)
    await db.commit()

    assert granted == 5
    assert member.coin_balance == 5
    assert order.coins_earned == 5
    assert order.coins_awarded is True
    assert order.coins_pending == 0
    assert order.feedback_food == 5
    assert order.feedback_service == 4
    assert order.feedback_at is not None


async def test_small_order_earns_nothing_even_with_feedback(db, member):
    order = await _collected_order(db, member, 3000)  # ₪30, under the minimum
    await db.commit()
    assert order.coins_pending == 0

    granted = await submit_feedback(db, order, member, food=5, service=5)
    await db.commit()

    assert granted == 0
    assert member.coin_balance == 0
    # The ratings are still recorded — they are useful regardless.
    assert order.feedback_food == 5


async def test_redeemed_coins_lower_the_earn_basis(db, member):
    """5% is taken on what was actually paid, not the pre-discount total."""
    await record_coins(db, member, 500, CoinTxKind.signup_bonus)
    await db.commit()

    # ₪100 order, 20 coins redeemed = ₪20 off, so ₪80 paid -> 4 coins.
    order = await _collected_order(db, member, 10000, redeem=20)
    await db.commit()
    assert order.total_agorot == 8000
    assert order.coins_pending == 4


async def test_redeeming_can_drop_an_order_below_the_minimum(db, member):
    await record_coins(db, member, 500, CoinTxKind.signup_bonus)
    await db.commit()

    # ₪50 order, 20 coins = ₪20 off -> ₪30 paid, under the ₪45 minimum.
    order = await _collected_order(db, member, 5000, redeem=20)
    await db.commit()
    assert order.total_agorot == 3000
    assert order.coins_pending == 0


# --- the 10-hour window ----------------------------------------------------


async def test_feedback_after_the_window_records_but_grants_nothing(db, member):
    order = await _collected_order(db, member, 10000)
    hours = settings.loyalty.feedback_window_hours
    order.collected_at = datetime.now(timezone.utc) - timedelta(hours=hours + 1)
    await db.commit()

    assert feedback_window_open(order) is False
    granted = await submit_feedback(db, order, member, food=3, service=3)
    await db.commit()

    assert granted == 0
    assert member.coin_balance == 0
    assert order.coins_pending == 0, "forfeited, not left dangling"
    assert order.feedback_food == 3, "ratings still recorded"


async def test_feedback_just_inside_the_window_still_pays(db, member):
    order = await _collected_order(db, member, 10000)
    hours = settings.loyalty.feedback_window_hours
    order.collected_at = datetime.now(timezone.utc) - timedelta(hours=hours - 1)
    await db.commit()

    assert feedback_window_open(order) is True
    assert await submit_feedback(db, order, member, food=4, service=5) == 5


# --- guards ----------------------------------------------------------------


async def test_feedback_cannot_be_submitted_twice(db, member):
    order = await _collected_order(db, member, 10000)
    await db.commit()
    await submit_feedback(db, order, member, food=5, service=5)
    await db.commit()
    balance = member.coin_balance

    with pytest.raises(HTTPException) as exc:
        await submit_feedback(db, order, member, food=1, service=1)
    assert exc.value.status_code == 400
    assert member.coin_balance == balance, "no double award"


async def test_feedback_requires_a_collected_order(db, member):
    item = await _item(db, 10000)
    order = await create_order(db, member, [(item.id, 1)], "", 0)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await submit_feedback(db, order, member, food=5, service=5)
    assert exc.value.status_code == 400


async def test_cancelling_before_feedback_grants_nothing(db, member):
    item = await _item(db, 10000)
    order = await create_order(db, member, [(item.id, 1)], "", 0)
    await advance_order_status(db, order, OrderStatus.cancelled)
    await db.commit()

    assert order.coins_pending == 0
    assert member.coin_balance == 0


# --- coin value and expiry -------------------------------------------------


def test_a_coin_is_worth_one_shekel():
    from app.services import agorot_per_coin

    assert agorot_per_coin() == 100


async def test_redemption_uses_the_configured_coin_value(db, member):
    """100 coins should now take ₪100 off, not ₪10."""
    from app.services import agorot_per_coin

    await record_coins(db, member, 500, CoinTxKind.signup_bonus)
    await db.commit()

    item = await _item(db, 20000)  # ₪200
    order = await create_order(db, member, [(item.id, 1)], "", 100)
    await db.commit()

    assert order.discount_agorot == 100 * agorot_per_coin() == 10000
    assert order.total_agorot == 10000


async def test_credits_carry_an_expiry_date(db, member):
    from app.services import coin_expiry_for

    tx = await record_coins(db, member, 50, CoinTxKind.signup_bonus)
    await db.commit()

    assert tx.expires_at is not None
    expected = coin_expiry_for()
    assert abs((tx.expires_at - expected).total_seconds()) < 60


async def test_debits_never_expire(db, member):
    await record_coins(db, member, 50, CoinTxKind.signup_bonus)
    tx = await record_coins(db, member, -10, CoinTxKind.redeem)
    await db.commit()

    assert tx.expires_at is None


async def test_coins_lapse_after_the_expiry_window(db, member):
    from app.services import expire_coins

    tx = await record_coins(db, member, 40, CoinTxKind.signup_bonus)
    tx.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()

    lapsed = await expire_coins(db, member)
    await db.commit()

    assert lapsed == 40
    assert member.coin_balance == 0


async def test_unexpired_coins_survive(db, member):
    from app.services import expire_coins

    await record_coins(db, member, 40, CoinTxKind.signup_bonus)
    await db.commit()

    assert await expire_coins(db, member) == 0
    assert member.coin_balance == 40


async def test_only_the_unspent_part_of_a_credit_lapses(db, member):
    from app.services import expire_coins

    tx = await record_coins(db, member, 100, CoinTxKind.signup_bonus)
    await record_coins(db, member, -30, CoinTxKind.redeem)
    await db.commit()
    assert member.coin_balance == 70

    tx.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()

    assert await expire_coins(db, member) == 70
    assert member.coin_balance == 0


async def test_spending_consumes_the_oldest_credits_first(db, member):
    """FIFO, so coins closest to expiring are the ones spent."""
    from app.services import expire_coins

    old = await record_coins(db, member, 50, CoinTxKind.signup_bonus)
    fresh = await record_coins(db, member, 50, CoinTxKind.earn)
    fresh.expires_at = datetime.now(timezone.utc) + timedelta(days=365)
    await db.commit()

    await record_coins(db, member, -50, CoinTxKind.redeem)
    await db.commit()
    assert old.consumed == 50, "the oldest credit should be spent first"
    assert fresh.consumed == 0

    # Expiring the old (now fully spent) credit must take nothing further.
    old.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()
    assert await expire_coins(db, member) == 0
    assert member.coin_balance == 50


async def test_expiry_is_recorded_in_the_ledger(db, member):
    from sqlalchemy import select

    from app.models import CoinTransaction
    from app.services import expire_coins

    tx = await record_coins(db, member, 25, CoinTxKind.signup_bonus)
    tx.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()
    await expire_coins(db, member)
    await db.commit()

    rows = (
        await db.execute(
            select(CoinTransaction).where(CoinTransaction.kind == CoinTxKind.expired)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].amount == -25
    assert rows[0].balance_after == 0


async def test_expiry_is_idempotent(db, member):
    from app.services import expire_coins

    tx = await record_coins(db, member, 30, CoinTxKind.signup_bonus)
    tx.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()

    assert await expire_coins(db, member) == 30
    await db.commit()
    assert await expire_coins(db, member) == 0, "must not double-charge"
    assert member.coin_balance == 0


async def test_lapsed_coins_cannot_be_spent(db, member):
    tx = await record_coins(db, member, 100, CoinTxKind.signup_bonus)
    tx.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()

    item = await _item(db, 20000)
    with pytest.raises(HTTPException):
        # The balance looks spendable until expiry runs, which record_coins
        # triggers before any debit.
        await create_order(db, member, [(item.id, 1)], "", 60)


def test_expiry_defaults_to_two_months():
    assert settings.loyalty.coin_expiry_days == 60


def test_expiry_can_be_disabled():
    from app.configuration import LoyaltySettings
    from app.services import coin_expiry_for

    assert LoyaltySettings(coin_expiry_days=0, _env_file=None).coin_expiry_days == 0
