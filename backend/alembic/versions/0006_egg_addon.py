"""Add eggs as a per-line option instead of a separate dish.

Revision ID: 0006_egg_addon
Revises: 0005_coin_expiry
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_egg_addon"
down_revision = "0005_coin_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "menu_items",
        sa.Column(
            "allows_egg", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "order_items",
        sa.Column("eggs", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "order_items",
        sa.Column(
            "egg_price_agorot", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # Every hummus can take an egg.
    op.execute("UPDATE menu_items SET allows_egg = true WHERE category = 'hummus'")

    # "חומוס ביצה" was never a real dish. Retire it rather than delete, so any
    # historical order line keeps resolving; its name/price are snapshotted.
    op.execute(
        "UPDATE menu_items SET is_available = false, allows_egg = false "
        "WHERE name_he = 'חומוס ביצה'"
    )


def downgrade() -> None:
    op.drop_column("order_items", "egg_price_agorot")
    op.drop_column("order_items", "eggs")
    op.drop_column("menu_items", "allows_egg")
