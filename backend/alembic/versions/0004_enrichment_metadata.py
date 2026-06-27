"""Add is_narrative, taxonomy_version, parametric_inference to enrichment_cache.

Revision ID: 0004_enrichment_metadata
Revises: 0003_flashcard_pool
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_enrichment_metadata"
down_revision = "0003_flashcard_pool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # is_narrative: False = non-fiction without narrative structure.
    # Trope extraction is skipped; Tower 1 snapshot still generated.
    op.add_column(
        "enrichment_cache",
        sa.Column("is_narrative", sa.Boolean(), nullable=False, server_default="true"),
    )

    # taxonomy_version: integer stamped at enrichment time.
    # Compared against settings.TAXONOMY_VERSION to detect stale enrichments.
    op.add_column(
        "enrichment_cache",
        sa.Column("taxonomy_version", sa.Integer(), nullable=False, server_default="0"),
    )

    # parametric_inference: True = Stage 2 LLM inference used (metadata was insufficient).
    # Confidence scores for these entries carry an automatic -0.1 discount.
    op.add_column(
        "enrichment_cache",
        sa.Column(
            "parametric_inference", sa.Boolean(), nullable=False, server_default="false"
        ),
    )

    # Mark known non-narrative works immediately.
    # These will skip _run_llm_extraction on any future re-enrichment run.
    op.execute("""
        UPDATE enrichment_cache
        SET is_narrative = false
        WHERE work_uuid IN (
            SELECT w.work_uuid
            FROM works w
            WHERE w.title IN (
                'Meditations',
                'Sapiens',
                'Thinking, Fast and Slow',
                'The Will to Change'
            )
        )
    """)


def downgrade() -> None:
    op.drop_column("enrichment_cache", "parametric_inference")
    op.drop_column("enrichment_cache", "taxonomy_version")
    op.drop_column("enrichment_cache", "is_narrative")
