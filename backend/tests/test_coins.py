"""The coin ledger must always reconcile with the cached balance."""

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import CoinTransaction, CoinTxKind, MenuItem, OrderStatus
from app.services import (
    AGOROT_PER_COIN,
    advance_order_status,
    coins_for_amount,
    create_order,
    max_redeemable_coins,
    record_coins,
)


async def _menu(db):
    items = [
        MenuItem(name_he="חומוס", category="hummus", price_agorot=4200),
        MenuItem(name_he="פיתה", category="sides", price_agorot=600),
        MenuItem(name_he="לא זמין", category="sides", price_agorot=100, is_available=False),
    ]
    db.add_all(items)
    await db.flush()
    return items


async def _ledger_sum(db, user_id: int) -> int:
    return (
        await db.execute(
            select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
                CoinTransaction.user_id == user_id
            )
        )
    ).scalar()


def test_coins_for_amount_rounds_down_to_whole_shekels():
    assert coins_for_amount(4200) == 42
    assert coins_for_amount(4299) == 42
    assert coins_for_amount(99) == 0


def test_max_redeemable_is_capped_at_half_the_bill():
    # 100 ILS bill, huge balance -> at most 50 ILS worth = 500 coins.
    assert max_redeemable_coins(10_000, 10_000) == 5_000 // AGOROT_PER_COIN
    # Limited by what the member actually holds.
    assert max_redeemable_coins(10_000, 120) == 120


async def test_record_coins_updates_balance_and_ledger(db, member):
    await record_coins(db, member, 50, CoinTxKind.signup_bonus, reason="bonus")
    await db.commit()

    assert member.coin_balance == 50
    assert member.lifetime_coins_earned == 50
    assert await _ledger_sum(db, member.id) == 50


async def test_record_coins_rejects_overdraft(db, member):
    with pytest.raises(HTTPException) as exc:
        await record_coins(db, member, -10, CoinTxKind.redeem)
    assert exc.value.status_code == 400
    assert member.coin_balance == 0


async def test_refund_does_not_inflate_lifetime_earned(db, member):
    await record_coins(db, member, 100, CoinTxKind.signup_bonus)
    await record_coins(db, member, -40, CoinTxKind.redeem)
    await record_coins(db, member, 40, CoinTxKind.refund)
    await db.commit()

    assert member.coin_balance == 100
    # The refund restores balance but is not new earning.
    assert member.lifetime_coins_earned == 100


async def test_order_totals_and_earn_on_collection(db, member):
    hummus, pita, _ = await _menu(db)
    order = await create_order(db, member, [(hummus.id, 2), (pita.id, 1)], "", 0)
    await db.commit()

    assert order.subtotal_agorot == 4200 * 2 + 600
    assert order.total_agorot == order.subtotal_agorot
    assert order.coins_earned == 0  # not awarded until collected

    await advance_order_status(db, order, OrderStatus.preparing)
    await advance_order_status(db, order, OrderStatus.ready)
    await advance_order_status(db, order, OrderStatus.collected)
    await db.commit()

    assert order.coins_awarded is True
    assert order.coins_earned == coins_for_amount(order.total_agorot)
    assert member.coin_balance == order.coins_earned
    assert order.payment_status.value == "paid"
    assert await _ledger_sum(db, member.id) == member.coin_balance


async def test_redeeming_coins_discounts_the_order(db, member):
    hummus, _, _ = await _menu(db)
    await record_coins(db, member, 1000, CoinTxKind.signup_bonus)
    await db.commit()

    # 42 ILS bill -> half is 21 ILS -> at most 210 coins.
    order = await create_order(db, member, [(hummus.id, 1)], "", 210)
    await db.commit()

    assert order.discount_agorot == 210 * AGOROT_PER_COIN
    assert order.total_agorot == 4200 - 2100
    assert member.coin_balance == 1000 - 210
    assert await _ledger_sum(db, member.id) == member.coin_balance


async def test_redeeming_more_than_allowed_is_rejected(db, member):
    hummus, _, _ = await _menu(db)
    await record_coins(db, member, 5000, CoinTxKind.signup_bonus)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await create_order(db, member, [(hummus.id, 1)], "", 5000)
    assert exc.value.status_code == 400


async def test_cancelling_refunds_spent_coins(db, member):
    hummus, _, _ = await _menu(db)
    await record_coins(db, member, 500, CoinTxKind.signup_bonus)
    await db.commit()

    order = await create_order(db, member, [(hummus.id, 1)], "", 200)
    await db.commit()
    assert member.coin_balance == 300

    await advance_order_status(db, order, OrderStatus.cancelled)
    await db.commit()

    assert member.coin_balance == 500
    assert order.coins_earned == 0
    assert await _ledger_sum(db, member.id) == 500


async def test_collected_order_cannot_change_status_again(db, member):
    hummus, _, _ = await _menu(db)
    order = await create_order(db, member, [(hummus.id, 1)], "", 0)
    await advance_order_status(db, order, OrderStatus.collected)
    await db.commit()
    awarded = member.coin_balance

    with pytest.raises(HTTPException):
        await advance_order_status(db, order, OrderStatus.cancelled)

    # No double-award, no refund out of a terminal state.
    assert member.coin_balance == awarded


async def test_unavailable_item_is_rejected(db, member):
    _, _, gone = await _menu(db)
    with pytest.raises(HTTPException) as exc:
        await create_order(db, member, [(gone.id, 1)], "", 0)
    assert exc.value.status_code == 400


async def test_unknown_item_is_rejected(db, member):
    with pytest.raises(HTTPException) as exc:
        await create_order(db, member, [(9999, 1)], "", 0)
    assert exc.value.status_code == 400


async def test_duplicate_cart_lines_are_merged(db, member):
    hummus, _, _ = await _menu(db)
    order = await create_order(db, member, [(hummus.id, 1), (hummus.id, 2)], "", 0)
    await db.commit()

    assert len(order.items) == 1
    assert order.items[0].quantity == 3
    assert order.subtotal_agorot == 4200 * 3
