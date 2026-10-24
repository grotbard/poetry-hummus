"""Track members who asked an admin to confirm their phone.

Revision ID: 0010_approval_request
Revises: 0009_phone_verification
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_approval_request"
down_revision = "0009_phone_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "approval_requested_at")
