"""Hold earned coins until the member rates the order.

Revision ID: 0004_order_feedback
Revises: 0003_menu_categories
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_order_feedback"
down_revision = "0003_menu_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("coins_pending", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("orders", sa.Column("feedback_food", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("feedback_service", sa.Integer(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Ratings are a 1-5 scale; reject anything else at the database level.
    op.create_check_constraint(
        "ck_orders_feedback_food_range",
        "orders",
        "feedback_food IS NULL OR (feedback_food BETWEEN 1 AND 5)",
    )
    op.create_check_constraint(
        "ck_orders_feedback_service_range",
        "orders",
        "feedback_service IS NULL OR (feedback_service BETWEEN 1 AND 5)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_feedback_service_range", "orders", type_="check")
    op.drop_constraint("ck_orders_feedback_food_range", "orders", type_="check")
    op.drop_column("orders", "feedback_at")
    op.drop_column("orders", "feedback_service")
    op.drop_column("orders", "feedback_food")
    op.drop_column("orders", "coins_pending")
