"""Add enrichment pipeline fields to Work and EnrichmentCache.

Revision ID: 0002_enrichment_pipeline
Revises: 0001_initial
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_enrichment_pipeline"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Work table additions ---
    op.add_column(
        "works",
        sa.Column(
            "enrichment_status", sa.String(), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "works",
        sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
    )

    # --- EnrichmentCache table additions ---
    op.add_column(
        "enrichment_cache", sa.Column("last_completed_step", sa.String(), nullable=True)
    )
    op.add_column(
        "enrichment_cache", sa.Column("description", sa.String(), nullable=True)
    )
    op.add_column(
        "enrichment_cache",
        sa.Column("raw_categories", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "enrichment_cache", sa.Column("subject_tags", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "enrichment_cache", sa.Column("series_raw", sa.String(), nullable=True)
    )
    op.add_column("enrichment_cache", sa.Column("olid", sa.String(), nullable=True))
    op.add_column(
        "enrichment_cache",
        sa.Column("tower1_snapshot", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "enrichment_cache",
        sa.Column("sentiment_snippets", postgresql.JSONB(), nullable=True),
    )

    # Change hallucination_verified from boolean to varchar
    op.drop_column("enrichment_cache", "hallucination_verified")
    op.add_column(
        "enrichment_cache",
        sa.Column(
            "hallucination_verified",
            sa.String(),
            nullable=True,
            server_default="unverifiable",
        ),
    )
    op.alter_column("enrichment_cache", "hallucination_verified", server_default=None)


def downgrade() -> None:
    # Revert hallucination_verified back to boolean
    op.drop_column("enrichment_cache", "hallucination_verified")
    op.add_column(
        "enrichment_cache",
        sa.Column(
            "hallucination_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.drop_column("enrichment_cache", "sentiment_snippets")
    op.drop_column("enrichment_cache", "tower1_snapshot")
    op.drop_column("enrichment_cache", "olid")
    op.drop_column("enrichment_cache", "series_raw")
    op.drop_column("enrichment_cache", "subject_tags")
    op.drop_column("enrichment_cache", "raw_categories")
    op.drop_column("enrichment_cache", "description")
    op.drop_column("enrichment_cache", "last_completed_step")

    op.drop_column("works", "publication_date")
    op.drop_column("works", "enrichment_status")
