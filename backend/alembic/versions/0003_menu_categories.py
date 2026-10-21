"""Add menu_categories so admins control group display order.

Revision ID: 0003_menu_categories
Revises: 0002_menu_image
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_menu_categories"
down_revision = "0002_menu_image"
branch_labels = None
depends_on = None

# Seeded in the intended display order, hummus first and desserts last.
DEFAULTS = [
    ("hummus", "חומוסים", 0),
    ("mains", "עיקריות", 1),
    ("sides", "תוספות וסלטים", 2),
    ("drinks", "שתייה", 3),
    ("desserts", "קינוחים", 4),
    ("other", "שונות", 5),
]


def upgrade() -> None:
    table = op.create_table(
        "menu_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label_he", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_menu_categories_key", "menu_categories", ["key"], unique=True)
    op.create_index("ix_menu_categories_sort_order", "menu_categories", ["sort_order"])

    op.bulk_insert(
        table,
        [
            {"key": key, "label_he": label, "sort_order": order}
            for key, label, order in DEFAULTS
        ],
    )

    # Any category already in use but not listed above goes to the end,
    # so no existing item loses its group.
    op.execute(
        sa.text(
            """
            INSERT INTO menu_categories (key, label_he, sort_order)
            SELECT DISTINCT m.category, m.category, 100
            FROM menu_items m
            WHERE m.category NOT IN (SELECT key FROM menu_categories)
            """
        )
    )


def downgrade() -> None:
    op.drop_table("menu_categories")
