"""Add partial_retry_count to enrichment_cache for stuck partial sweeper.

Revision ID: 0006_partial_retry_count
Revises: 0005_interested_signal
Create Date: 2026-06-13

The sweeper re-queues books stuck in "partial" status; after N retries
(checked via partial_retry_count) the book is marked "partial_failed".
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_partial_retry_count"
down_revision = "0005_interested_signal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "enrichment_cache",
        sa.Column(
            "partial_retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("enrichment_cache", "partial_retry_count")
