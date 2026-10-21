"""Initial schema: users, menu, orders, rewards, coin ledger, activity log.

Revision ID: 0001_initial
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

user_role = sa.Enum("member", "admin", name="user_role")
order_status = sa.Enum(
    "pending", "preparing", "ready", "collected", "cancelled", name="order_status"
)
payment_status = sa.Enum("unpaid", "paid", "refunded", name="payment_status")
coin_tx_kind = sa.Enum(
    "earn", "redeem", "signup_bonus", "admin_adjust", "refund", name="coin_tx_kind"
)

# Column-level references to the types created above.
user_role_col = postgresql.ENUM(name="user_role", create_type=False)
order_status_col = postgresql.ENUM(name="order_status", create_type=False)
payment_status_col = postgresql.ENUM(name="payment_status", create_type=False)
coin_tx_kind_col = postgresql.ENUM(name="coin_tx_kind", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (user_role, order_status, payment_status, coin_tx_kind):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("google_sub", sa.String(64), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("picture_url", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("role", user_role_col, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("coin_balance", sa.Integer(), nullable=False),
        sa.Column("lifetime_coins_earned", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "menu_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name_he", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("description_he", sa.Text(), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("price_agorot", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("is_vegan", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_menu_items_category", "menu_items", ["category"])
    op.create_index("ix_menu_items_is_available", "menu_items", ["is_available"])

    op.create_table(
        "rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name_he", sa.String(200), nullable=False),
        sa.Column("description_he", sa.Text(), nullable=False),
        sa.Column("cost_coins", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_number", sa.String(20), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", order_status_col, nullable=False),
        sa.Column("payment_status", payment_status_col, nullable=False),
        sa.Column("payment_reference", sa.String(100), nullable=True),
        sa.Column("subtotal_agorot", sa.Integer(), nullable=False),
        sa.Column("discount_agorot", sa.Integer(), nullable=False),
        sa.Column("total_agorot", sa.Integer(), nullable=False),
        sa.Column("coins_spent", sa.Integer(), nullable=False),
        sa.Column("coins_earned", sa.Integer(), nullable=False),
        sa.Column("coins_awarded", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])
    op.create_index(
        "ix_orders_user_created", "orders", ["user_id", sa.text("created_at DESC")]
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_id",
            sa.Integer(),
            sa.ForeignKey("menu_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name_snapshot", sa.String(200), nullable=False),
        sa.Column("unit_price_agorot", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_agorot", sa.Integer(), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "coin_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reward_id",
            sa.Integer(),
            sa.ForeignKey("rewards.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("kind", coin_tx_kind_col, nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_coin_transactions_user_id", "coin_transactions", ["user_id"])
    op.create_index("ix_coin_transactions_order_id", "coin_transactions", ["order_id"])
    op.create_index("ix_coin_transactions_created_at", "coin_transactions", ["created_at"])
    op.create_index(
        "ix_cointx_user_created",
        "coin_transactions",
        ["user_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "activity_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_activity_log_user_id", "activity_log", ["user_id"])
    op.create_index("ix_activity_log_action", "activity_log", ["action"])
    op.create_index("ix_activity_log_created_at", "activity_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("activity_log")
    op.drop_table("coin_transactions")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("rewards")
    op.drop_table("menu_items")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_type in (coin_tx_kind, payment_status, order_status, user_role):
        enum_type.drop(bind, checkfirst=True)
