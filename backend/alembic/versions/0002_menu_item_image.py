"""Add menu_items.image_url for uploaded item photos.

Revision ID: 0002_menu_image
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_menu_image"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menu_items", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("menu_items", "image_url")
