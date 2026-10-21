"""Give earned coins an expiry date.

Revision ID: 0005_coin_expiry
Revises: 0004_order_feedback
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_coin_expiry"
down_revision = "0004_order_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE coin_tx_kind ADD VALUE IF NOT EXISTS 'expired'")
    op.add_column(
        "coin_transactions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "coin_transactions",
        sa.Column("consumed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_coin_transactions_expires_at", "coin_transactions", ["expires_at"]
    )
    # Coins already spent must not be handed out again by the FIFO scan, so
    # retire existing credits up to whatever each member has already used.
    op.execute(
        """
        WITH spent AS (
            SELECT user_id, COALESCE(SUM(-amount), 0) AS total
            FROM coin_transactions WHERE amount < 0 GROUP BY user_id
        ),
        ranked AS (
            SELECT c.id, c.amount, c.user_id,
                   COALESCE(SUM(c.amount) OVER (
                       PARTITION BY c.user_id
                       ORDER BY c.created_at, c.id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                   ), 0) AS prior
            FROM coin_transactions c WHERE c.amount > 0
        )
        UPDATE coin_transactions t
        SET consumed = LEAST(
            r.amount, GREATEST(0, COALESCE(s.total, 0) - r.prior)
        )
        FROM ranked r
        LEFT JOIN spent s ON s.user_id = r.user_id
        WHERE t.id = r.id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_coin_transactions_expires_at", table_name="coin_transactions")
    op.drop_column("coin_transactions", "consumed")
    op.drop_column("coin_transactions", "expires_at")
    # The enum value is left in place; removing a PG enum member is unsafe.
