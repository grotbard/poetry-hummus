"""Invite a friend: referral codes and tracked invitations.

Revision ID: 0008_referrals
Revises: 0007_rename_pita
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_referrals"
down_revision = "0007_rename_pita"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE coin_tx_kind ADD VALUE IF NOT EXISTS 'referral'")
    op.add_column("users", sa.Column("referral_code", sa.String(16), nullable=True))
    op.create_index(
        "ix_users_referral_code", "users", ["referral_code"], unique=True
    )

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "inviter_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inviter_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invitee_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # A member can only ever be invited once, by one person.
        sa.UniqueConstraint("invitee_id", name="uq_referrals_invitee"),
    )
    op.create_index("ix_referrals_inviter_id", "referrals", ["inviter_id"])
    op.create_index("ix_referrals_invitee_id", "referrals", ["invitee_id"])


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_column("users", "referral_code")
    # The enum value is left in place; removing a PG enum member is unsafe.
