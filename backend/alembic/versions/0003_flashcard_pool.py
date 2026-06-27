"""Add flashcard_pool flag to enrichment_cache.

Revision ID: 0003_flashcard_pool
Revises: 0002_enrichment_pipeline
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003_flashcard_pool"
down_revision: Union[str, None] = "0002_enrichment_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enrichment_cache",
        sa.Column(
            "flashcard_pool",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("enrichment_cache", "flashcard_pool")
