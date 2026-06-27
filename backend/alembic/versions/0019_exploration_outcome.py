"""Add exploration_outcome to event_type_enum.

Revision ID: 0019_exploration_outcome
Revises: 0018_mystery_nonfiction_v11
Create Date: 2026-06-21
"""

from alembic import op

revision = "0019_exploration_outcome"
down_revision = "0018_mystery_nonfiction_v11"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS 'exploration_outcome'"
    )


def downgrade():
    pass
