"""Initial schema creation and taxonomy seed.

Creates all tables from ORM models and populates the trope taxonomy DAG.

Revision ID: 0001_initial
Revises: None
Create Date: 2026-06-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Create enum types explicitly (with IF NOT EXISTS guard) ---
    for enum_name, values in [
        ("tbr_status_enum", ["active", "dropped", "converted_to_read"]),
        ("rec_source_enum", ["tbr", "vector", "llm"]),
        (
            "rec_status_enum",
            [
                "delivered",
                "finished",
                "abandoned",
                "not_interested",
                "still_reading",
                "havent_started",
                "reread",
            ],
        ),
        (
            "event_type_enum",
            [
                "logged_read",
                "not_interested",
                "reread",
                "checkpoint_update",
                "query",
                "tbr_add",
            ],
        ),
        ("abandonment_stage_enum", ["barely_started", "halfway", "nearly_finished"]),
    ]:
        op.execute(
            f"CREATE TYPE {enum_name} AS ENUM ({','.join(repr(v) for v in values)})"
        )
        op.execute("COMMIT")

    # --- Persons (authors) ---
    op.create_table(
        "persons",
        sa.Column(
            "person_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("canonical_name", sa.String(), nullable=False),
    )

    # --- Pen Names ---
    op.create_table(
        "pen_names",
        sa.Column(
            "pen_name_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "person_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_uuid"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("primary_genre", sa.String(), nullable=True),
    )

    # --- Works ---
    op.create_table(
        "works",
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
        sa.Column("aggregate_rating", sa.Float(), nullable=True),
        sa.Column(
            "person_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_uuid"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )

    # --- Editions ---
    op.create_table(
        "editions",
        sa.Column(
            "edition_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.work_uuid"),
            nullable=False,
        ),
        sa.Column("isbn", sa.String(), nullable=True),
        sa.Column("format", sa.String(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("cover_url", sa.String(), nullable=True),
        sa.Column("publisher", sa.String(), nullable=True),
        sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Series ---
    op.create_table(
        "series",
        sa.Column(
            "series_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column(
            "person_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_uuid"),
            nullable=False,
        ),
        sa.Column("total_core_works", sa.Integer(), nullable=True),
    )

    # --- Series-Works join table ---
    op.create_table(
        "series_works",
        sa.Column(
            "series_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("series.series_uuid"),
            primary_key=True,
        ),
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.work_uuid"),
            primary_key=True,
        ),
        sa.Column("order_float", sa.Float(), nullable=False),
        sa.Column(
            "is_core_storyline",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # --- Tropes ---
    op.create_table(
        "tropes",
        sa.Column(
            "trope_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("canonical_name", sa.String(), nullable=False, unique=True),
        sa.Column(
            "depth_level", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "is_root_hub", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    # --- Trope Parents (DAG edges) ---
    op.create_table(
        "trope_parents",
        sa.Column(
            "trope_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tropes.trope_uuid"),
            primary_key=True,
        ),
        sa.Column(
            "parent_trope_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tropes.trope_uuid"),
            primary_key=True,
        ),
    )

    # --- Trope Aliases ---
    op.create_table(
        "trope_aliases",
        sa.Column(
            "alias_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "trope_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tropes.trope_uuid"),
            nullable=False,
        ),
        sa.Column("alias_text", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
    )

    # --- Book-Trope mapping ---
    op.create_table(
        "book_tropes",
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.work_uuid"),
            primary_key=True,
        ),
        sa.Column(
            "trope_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tropes.trope_uuid"),
            primary_key=True,
        ),
        sa.Column("confidence_score", sa.Float(), nullable=False),
    )

    # --- Orphan Queue ---
    op.create_table(
        "orphan_queue",
        sa.Column("tag_text", sa.String(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "frequency_count", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("llm_closest_match", sa.String(), nullable=True),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
    )

    # --- Users ---
    op.create_table(
        "users",
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("calibration_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "calibration_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # --- User Profiles (Tower 1 + Tower 2) ---
    op.create_table(
        "user_profiles",
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_uuid"),
            primary_key=True,
        ),
        sa.Column("darkness_tolerance", sa.Float(), nullable=True),
        sa.Column("angst_level", sa.Float(), nullable=True),
        sa.Column("thematic_density", sa.Float(), nullable=True),
        sa.Column("pacing_preference", sa.Float(), nullable=True),
        sa.Column("standalone_preference", sa.Float(), nullable=True),
        sa.Column("exploration_tolerance", sa.Float(), nullable=True),
        sa.Column("explicit_content_level", sa.Float(), nullable=True),
        sa.Column("romance_centrality", sa.Float(), nullable=True),
        sa.Column("tower2_embedding", sa.ARRAY(sa.Float()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- User Profile Snapshots ---
    op.create_table(
        "user_profile_snapshots",
        sa.Column(
            "snapshot_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_uuid"),
            nullable=False,
            index=True,
        ),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "taken_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trigger_event", sa.String(), nullable=False),
    )

    # --- Interaction Events ---
    op.create_table(
        "interaction_events",
        sa.Column(
            "event_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_uuid"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.work_uuid"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "event_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("query_text", sa.String(), nullable=True),
        sa.Column("mood_tags", postgresql.JSONB(), nullable=True),
        sa.Column("time_of_day", sa.String(), nullable=True),
        sa.Column("day_of_week", sa.String(), nullable=True),
        sa.Column("tower1_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("stated_rating", sa.Integer(), nullable=True),
        sa.Column("abandonment_stage", sa.String(), nullable=True),
    )

    # --- TBR Entries ---
    op.create_table(
        "tbr_entries",
        sa.Column(
            "tbr_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_uuid"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.work_uuid"),
            nullable=False,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("add_query_text", sa.String(), nullable=True),
        sa.Column("add_mood_tags", postgresql.JSONB(), nullable=True),
        sa.Column("add_time_of_day", sa.String(), nullable=True),
        sa.Column("add_day_of_week", sa.String(), nullable=True),
        sa.Column(
            "priority_score", sa.Float(), nullable=False, server_default=sa.text("1.0")
        ),
        sa.Column(
            "skip_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )

    # --- Recommendation Log ---
    op.create_table(
        "recommendations_log",
        sa.Column(
            "rec_uuid",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_uuid"),
            nullable=False,
            index=True,
        ),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.work_uuid"),
            nullable=False,
        ),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("query_text", sa.String(), nullable=False),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="delivered"),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_notes", sa.String(), nullable=True),
    )

    # --- Enrichment Cache ---
    op.create_table(
        "enrichment_cache",
        sa.Column(
            "work_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.work_uuid"),
            primary_key=True,
        ),
        sa.Column("tavily_sentiment", sa.String(), nullable=True),
        sa.Column(
            "hallucination_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("community_buzz_score", sa.Float(), nullable=True),
        sa.Column(
            "cliffhanger_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("trigger_warnings", postgresql.JSONB(), nullable=True),
        sa.Column(
            "controversy_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "enriched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("refresh_due_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Tracked Authors ---
    op.create_table(
        "tracked_authors",
        sa.Column(
            "user_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_uuid"),
            primary_key=True,
        ),
        sa.Column(
            "person_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_uuid"),
            primary_key=True,
        ),
        sa.Column(
            "tracked_since",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_known_release_date", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Seed Taxonomy ---
    seed_taxonomy()


def seed_taxonomy() -> None:
    """Seed the trope taxonomy DAG from seed_data.py."""
    from sqlalchemy.orm import Session

    import app.models  # noqa: F401
    from app.taxonomy.seed_data import ROOT_HUBS, TROPE_NODES

    bind = op.get_bind()
    session = Session(bind=bind)

    all_nodes = {}

    for hub_name in ROOT_HUBS:
        session.execute(
            sa.text(
                "INSERT INTO tropes (canonical_name, depth_level, is_root_hub) "
                "VALUES (:name, 0, true) ON CONFLICT (canonical_name) DO NOTHING"
            ),
            {"name": hub_name},
        )
    session.flush()

    hubs = session.execute(
        sa.text(
            "SELECT canonical_name, trope_uuid FROM tropes WHERE is_root_hub = true"
        )
    ).all()
    for hub_name, hub_uuid in hubs:
        all_nodes[hub_name] = hub_uuid

    for node in TROPE_NODES:
        name = node["name"]
        parent_depths = []
        for p in node["parents"]:
            parent_row = session.execute(
                sa.text("SELECT depth_level FROM tropes WHERE canonical_name = :name"),
                {"name": p},
            ).first()
            if parent_row:
                parent_depths.append(parent_row[0])

        depth = max(parent_depths) + 1 if parent_depths else 1

        session.execute(
            sa.text(
                "INSERT INTO tropes (canonical_name, depth_level, is_root_hub) "
                "VALUES (:name, :depth, false) ON CONFLICT (canonical_name) DO NOTHING"
            ),
            {"name": name, "depth": depth},
        )
    session.flush()

    all_rows = session.execute(
        sa.text("SELECT canonical_name, trope_uuid FROM tropes")
    ).all()
    for row_name, row_uuid in all_rows:
        all_nodes[row_name] = row_uuid

    for node in TROPE_NODES:
        name = node["name"]
        child_uuid = all_nodes.get(name)
        if not child_uuid:
            continue
        for parent_name in node["parents"]:
            parent_uuid = all_nodes.get(parent_name)
            if not parent_uuid:
                continue
            session.execute(
                sa.text(
                    "INSERT INTO trope_parents (trope_uuid, parent_trope_uuid) "
                    "VALUES (:child, :parent) ON CONFLICT DO NOTHING"
                ),
                {"child": str(child_uuid), "parent": str(parent_uuid)},
            )

    session.commit()
    session.close()


def downgrade() -> None:
    op.drop_table("tracked_authors")
    op.drop_table("enrichment_cache")
    op.drop_table("recommendations_log")
    op.drop_table("tbr_entries")
    op.drop_table("interaction_events")
    op.drop_table("user_profile_snapshots")
    op.drop_table("user_profiles")
    op.drop_table("users")
    op.drop_table("orphan_queue")
    op.drop_table("book_tropes")
    op.drop_table("trope_aliases")
    op.drop_table("trope_parents")
    op.drop_table("tropes")
    op.drop_table("series_works")
    op.drop_table("series")
    op.drop_table("editions")
    op.drop_table("works")
    op.drop_table("pen_names")
    op.drop_table("persons")

    for enum_name in [
        "tbr_status_enum",
        "rec_source_enum",
        "rec_status_enum",
        "event_type_enum",
        "abandonment_stage_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name} CASCADE")
