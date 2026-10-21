"""Eggs are a per-line add-on, not a dish."""

import pytest
from fastapi import HTTPException

from app.configuration import settings
from app.models import MenuItem
from app.services import create_order

EGG = settings.menu.egg_price_agorot


async def _hummus(db, price: int = 4200) -> MenuItem:
    item = MenuItem(
        name_he="חומוס המשורר", category="hummus", price_agorot=price, allows_egg=True
    )
    db.add(item)
    await db.flush()
    return item


async def _drink(db) -> MenuItem:
    item = MenuItem(
        name_he="קולה", category="drinks", price_agorot=1000, allows_egg=False
    )
    db.add(item)
    await db.flush()
    return item


def test_an_egg_costs_three_shekels():
    assert EGG == 300


async def test_order_without_eggs_is_unchanged(db, member):
    item = await _hummus(db)
    order = await create_order(db, member, [(item.id, 2)], "", 0)
    await db.commit()

    assert order.subtotal_agorot == 4200 * 2
    assert order.items[0].eggs == 0
    assert order.items[0].egg_price_agorot == 0


async def test_one_egg_adds_its_price(db, member):
    item = await _hummus(db)
    order = await create_order(db, member, [(item.id, 1, 1)], "", 0)
    await db.commit()

    assert order.subtotal_agorot == 4200 + EGG
    assert order.items[0].eggs == 1
    assert order.items[0].egg_price_agorot == EGG


async def test_multiple_eggs_on_one_plate(db, member):
    item = await _hummus(db)
    order = await create_order(db, member, [(item.id, 1, 3)], "", 0)
    await db.commit()

    assert order.subtotal_agorot == 4200 + 3 * EGG


async def test_eggs_scale_with_quantity(db, member):
    """Two plates with two eggs each means four eggs."""
    item = await _hummus(db)
    order = await create_order(db, member, [(item.id, 2, 2)], "", 0)
    await db.commit()

    assert order.subtotal_agorot == (4200 + 2 * EGG) * 2
    assert order.items[0].quantity == 2
    assert order.items[0].eggs == 2


async def test_same_dish_with_different_eggs_stays_two_lines(db, member):
    item = await _hummus(db)
    order = await create_order(db, member, [(item.id, 1, 0), (item.id, 1, 2)], "", 0)
    await db.commit()

    assert len(order.items) == 2
    assert order.subtotal_agorot == 4200 + (4200 + 2 * EGG)


async def test_same_dish_with_same_eggs_still_merges(db, member):
    item = await _hummus(db)
    order = await create_order(db, member, [(item.id, 1, 1), (item.id, 2, 1)], "", 0)
    await db.commit()

    assert len(order.items) == 1
    assert order.items[0].quantity == 3
    assert order.subtotal_agorot == (4200 + EGG) * 3


async def test_eggs_are_rejected_on_dishes_that_do_not_allow_them(db, member):
    drink = await _drink(db)
    with pytest.raises(HTTPException) as exc:
        await create_order(db, member, [(drink.id, 1, 1)], "", 0)
    assert exc.value.status_code == 400
    assert "קולה" in exc.value.detail


async def test_zero_eggs_on_a_dish_without_the_option_is_fine(db, member):
    drink = await _drink(db)
    order = await create_order(db, member, [(drink.id, 1, 0)], "", 0)
    await db.commit()
    assert order.subtotal_agorot == 1000


async def test_egg_price_is_snapshotted_on_the_line(db, member):
    """A later price change must not rewrite historical orders."""
    item = await _hummus(db)
    order = await create_order(db, member, [(item.id, 1, 1)], "", 0)
    await db.commit()

    assert order.items[0].egg_price_agorot == EGG
    assert order.items[0].line_total_agorot == 4200 + EGG
