"""Shared ordering for menu listings.

Items are grouped by their category's admin-set position, then by the item's
own position within the group. A category with no row sorts last rather than
dropping its items, so an item never vanishes because of a missing category.
"""

from sqlalchemy import Select, func, select

from .models import MenuCategory, MenuItem

# Sorts after any realistic sort_order, keeping unknown categories last.
UNRANKED = 10_000


def menu_ordered() -> Select:
    return (
        select(MenuItem)
        .outerjoin(MenuCategory, MenuCategory.key == MenuItem.category)
        .order_by(
            func.coalesce(MenuCategory.sort_order, UNRANKED),
            MenuItem.category,
            MenuItem.sort_order,
            MenuItem.id,
        )
    )
