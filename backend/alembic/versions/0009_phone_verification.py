"""Mandatory phone verification.

Revision ID: 0009_phone_verification
Revises: 0008_referrals
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_phone_verification"
down_revision = "0008_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Existing numbers were stored as typed (052-8498629); the column is now
    # E.164 and unique, so normalise before adding the index or it will clash
    # on numbers that differ only in punctuation.
    op.execute(
        r"""
        UPDATE users
        SET phone = '+972' || substring(regexp_replace(phone, '\D', '', 'g') from 2)
        WHERE phone IS NOT NULL
          AND phone NOT LIKE '+%'
          AND regexp_replace(phone, '\D', '', 'g') LIKE '0%'
        """
    )
    # Anything still not in E.164 cannot be trusted as an identity; clear it
    # rather than fail the migration, and the member re-enters it on next login.
    op.execute("UPDATE users SET phone = NULL WHERE phone IS NOT NULL AND phone NOT LIKE '+%'")

    # Should a duplicate survive, keep it on the oldest account only.
    op.execute(
        """
        UPDATE users SET phone = NULL
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (PARTITION BY phone ORDER BY id) AS rn
                FROM users WHERE phone IS NOT NULL
            ) ranked WHERE rn > 1
        )
        """
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    # Existing members keep their number but are NOT marked verified: they
    # confirm it on next sign-in, which is what makes verification mandatory.

    op.create_table(
        "phone_verifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_phone_verifications_phone", "phone_verifications", ["phone"])
    op.create_index(
        "ix_phone_verifications_created_at", "phone_verifications", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("phone_verifications")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "phone_verified_at")
