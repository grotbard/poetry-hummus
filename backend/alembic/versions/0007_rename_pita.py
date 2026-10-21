"""Rename the pita to "פיתה על הגז".

Revision ID: 0007_rename_pita
Revises: 0006_egg_addon
"""

from alembic import op

revision = "0007_rename_pita"
down_revision = "0006_egg_addon"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Order lines snapshot their own name, so past orders keep the old wording.
    op.execute(
        """
        UPDATE menu_items
        SET name_he = 'פיתה על הגז',
            name_en = 'Grilled Pita',
            description_he = 'פיתה חמה ישר מהגז'
        WHERE name_he = 'פיתה חמה'
        """
    )
    op.execute(
        """
        UPDATE rewards
        SET name_he = 'פיתה על הגז במתנה',
            description_he = 'פיתה חמה ישר מהגז'
        WHERE name_he = 'פיתה חמה במתנה'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE menu_items
        SET name_he = 'פיתה חמה',
            name_en = 'Warm Pita',
            description_he = 'פיתה טרייה מהטאבון'
        WHERE name_he = 'פיתה על הגז'
        """
    )
    op.execute(
        """
        UPDATE rewards
        SET name_he = 'פיתה חמה במתנה',
            description_he = 'פיתה טרייה מהטאבון'
        WHERE name_he = 'פיתה על הגז במתנה'
        """
    )
