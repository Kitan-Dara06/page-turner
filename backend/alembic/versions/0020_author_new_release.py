"""Add author_new_release to event_type_enum.

Revision ID: 0020_author_new_release
Revises: 0019_exploration_outcome
Create Date: 2026-06-21
"""

from alembic import op

revision = "0020_author_new_release"
down_revision = "0019_exploration_outcome"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS 'author_new_release'"
    )


def downgrade():
    pass
