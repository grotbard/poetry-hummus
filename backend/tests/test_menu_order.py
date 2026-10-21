"""Menu display order: category positions drive grouping, items sort within."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.menu_query import menu_ordered
from app.models import MenuCategory, MenuItem, User, UserRole
from app.routers.admin import reorder_categories, reorder_menu_items
from app.schemas import ReorderRequest


async def _fixture(db):
    db.add_all(
        [
            MenuCategory(key="hummus", label_he="חומוסים", sort_order=0),
            MenuCategory(key="desserts", label_he="קינוחים", sort_order=4),
            MenuCategory(key="drinks", label_he="שתייה", sort_order=3),
        ]
    )
    db.add_all(
        [
            MenuItem(name_he="מלבי", category="desserts", price_agorot=1800, sort_order=0),
            MenuItem(name_he="חומוס", category="hummus", price_agorot=4200, sort_order=0),
            MenuItem(name_he="פול", category="hummus", price_agorot=4500, sort_order=1),
            MenuItem(name_he="קולה", category="drinks", price_agorot=1000, sort_order=0),
        ]
    )
    await db.flush()
    admin = User(email="a@example.com", role=UserRole.admin)
    db.add(admin)
    await db.flush()
    return admin


async def _category_sequence(db) -> list[str]:
    rows = (await db.execute(menu_ordered())).scalars().all()
    seen: list[str] = []
    for item in rows:
        if item.category not in seen:
            seen.append(item.category)
    return seen


async def test_groups_follow_category_sort_order_not_the_alphabet(db):
    """'desserts' sorts before 'hummus' alphabetically; position must win."""
    await _fixture(db)
    assert await _category_sequence(db) == ["hummus", "drinks", "desserts"]


async def test_items_without_a_category_row_sort_last(db):
    await _fixture(db)
    db.add(MenuItem(name_he="מנה יתומה", category="mystery", price_agorot=100))
    await db.flush()

    sequence = await _category_sequence(db)
    assert sequence[-1] == "mystery", "unknown category must not disappear"
    assert len(sequence) == 4


async def test_reordering_categories_reorders_the_menu(db):
    admin = await _fixture(db)
    cats = {
        c.key: c.id
        for c in (await db.execute(select(MenuCategory))).scalars().all()
    }

    await reorder_categories(
        ReorderRequest(ids=[cats["desserts"], cats["drinks"], cats["hummus"]]),
        admin=admin,
        db=db,
    )
    assert await _category_sequence(db) == ["desserts", "drinks", "hummus"]


async def test_reordering_items_within_a_category(db):
    admin = await _fixture(db)
    hummus = (
        await db.execute(
            select(MenuItem).where(MenuItem.category == "hummus").order_by(MenuItem.sort_order)
        )
    ).scalars().all()
    original = [i.name_he for i in hummus]

    await reorder_menu_items(
        ReorderRequest(ids=[hummus[1].id, hummus[0].id]), admin=admin, db=db
    )

    after = (
        await db.execute(
            select(MenuItem).where(MenuItem.category == "hummus").order_by(MenuItem.sort_order)
        )
    ).scalars().all()
    assert [i.name_he for i in after] == list(reversed(original))


async def test_reordering_across_categories_is_rejected(db):
    """Positions are per-category, so a mixed list would corrupt both."""
    admin = await _fixture(db)
    a = (
        await db.execute(select(MenuItem).where(MenuItem.category == "hummus"))
    ).scalars().first()
    b = (
        await db.execute(select(MenuItem).where(MenuItem.category == "drinks"))
    ).scalars().first()

    with pytest.raises(HTTPException) as exc:
        await reorder_menu_items(ReorderRequest(ids=[a.id, b.id]), admin=admin, db=db)
    assert exc.value.status_code == 400


async def test_reordering_unknown_ids_is_rejected(db):
    admin = await _fixture(db)
    with pytest.raises(HTTPException) as exc:
        await reorder_menu_items(ReorderRequest(ids=[999999]), admin=admin, db=db)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await reorder_categories(ReorderRequest(ids=[999999]), admin=admin, db=db)
    assert exc.value.status_code == 400
