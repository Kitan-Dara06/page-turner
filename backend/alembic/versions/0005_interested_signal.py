"""Add INTERESTED to event_type_enum and rec_status_enum.

Revision ID: 0005_interested_signal
Revises: 0004_enrichment_metadata
Create Date: 2026-06-13

Postgres enums cannot be altered inside a transaction with the standard
ALTER TYPE ... ADD VALUE syntax. We use a PL/pgSQL DO block so the check
and the ADD VALUE are atomic and idempotent.
"""

from alembic import op
from sqlalchemy import text

revision = "0005_interested_signal"
down_revision = "0004_enrichment_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Extend event_type_enum with 'interested' if not already present.
    # The DO block makes this safe to run multiple times.
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'interested'
                  AND enumtypid = 'event_type_enum'::regtype
            ) THEN
                ALTER TYPE event_type_enum ADD VALUE 'interested';
            END IF;
        END
        $$;
    """))

    # Extend rec_status_enum with 'interested' if not already present.
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'interested'
                  AND enumtypid = 'rec_status_enum'::regtype
            ) THEN
                ALTER TYPE rec_status_enum ADD VALUE 'interested';
            END IF;
        END
        $$;
    """))


def downgrade() -> None:
    # Postgres does not support removing enum values without dropping and recreating the type.
    # Downgrade is intentionally a no-op.
    pass
