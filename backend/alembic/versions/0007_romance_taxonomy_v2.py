"""Seed v2.0 romance taxonomy nodes.

Revision ID: 0007_romance_taxonomy_v2
Revises: 0006_partial_retry_count
Create Date: 2026-06-14

Adds 28 new trope nodes for romance genre registers and tropes.
Uses raw SQL — fast, no ORM overhead.
"""

from sqlalchemy import text

from alembic import op

revision = "0007_romance_taxonomy_v2"
down_revision = "0006_partial_retry_count"
branch_labels = None
depends_on = None

# New nodes
NEW_NODES = [
    "Dark Romance",
    "Contemporary Romance",
    "Romantic Fantasy",
    "Historical Romance",
    "Paranormal Romance",
    "Sports Romance",
    "Workplace Romance",
    "MM Romance",
    "FF Romance",
    "Queer Romance",
    "Cozy Romance",
    "Romantic Comedy",
    "Fake Dating",
    "Friends to Lovers",
    "Surprise Pregnancy",
    "Age Gap Romance",
    "Billionaire Romance",
    "Small Town Romance",
    "Holiday Romance",
    "Instalove",
    "Love Triangle",
    "Hurt/Comfort",
    "Bodyguard Romance",
    "Roommate Romance",
    "Single Parent Romance",
    "Touch Her and Die",
    "Brothers Best Friend",
    "Bully Romance",
    "Stalker Romance",
    "Dark Reverse Harem",
]

# Parent relationships (child, parent)
NEW_PARENTS = [
    ("Dark Romance", "Relationship Dynamics"),
    ("Dark Romance", "Thematic Core"),
    ("Contemporary Romance", "Relationship Dynamics"),
    ("Contemporary Romance", "Grounded"),
    ("Romantic Fantasy", "Relationship Dynamics"),
    ("Romantic Fantasy", "Reality"),
    ("Historical Romance", "Relationship Dynamics"),
    ("Historical Romance", "Historical"),
    ("Paranormal Romance", "Relationship Dynamics"),
    ("Paranormal Romance", "Reality"),
    ("Sports Romance", "Relationship Dynamics"),
    ("Sports Romance", "Grounded"),
    ("Workplace Romance", "Relationship Dynamics"),
    ("Workplace Romance", "Grounded"),
    ("MM Romance", "Relationship Dynamics"),
    ("FF Romance", "Relationship Dynamics"),
    ("Queer Romance", "Relationship Dynamics"),
    ("Cozy Romance", "Relationship Dynamics"),
    ("Romantic Comedy", "Relationship Dynamics"),
    ("Fake Dating", "Relationship Dynamics"),
    ("Friends to Lovers", "Relationship Dynamics"),
    ("Surprise Pregnancy", "Relationship Dynamics"),
    ("Age Gap Romance", "Forbidden Romance"),
    ("Billionaire Romance", "Relationship Dynamics"),
    ("Small Town Romance", "Setting & Environment"),
    ("Small Town Romance", "Relationship Dynamics"),
    ("Holiday Romance", "Setting & Environment"),
    ("Holiday Romance", "Relationship Dynamics"),
    ("Instalove", "Relationship Dynamics"),
    ("Love Triangle", "Relationship Dynamics"),
    ("Love Triangle", "Interpersonal Conflict"),
    ("Hurt/Comfort", "Relationship Dynamics"),
    ("Hurt/Comfort", "Grief/Loss"),
    ("Bodyguard Romance", "Forced Proximity"),
    ("Roommate Romance", "Forced Proximity"),
    ("Single Parent Romance", "Relationship Dynamics"),
    ("Touch Her and Die", "Possessive Hero"),
    ("Brothers Best Friend", "Forbidden Romance"),
    ("Bully Romance", "Enemies to Lovers"),
    ("Bully Romance", "Dark Romance"),
    ("Stalker Romance", "Obsession"),
    ("Stalker Romance", "Dark Romance"),
    ("Dark Reverse Harem", "Reverse Harem"),
    ("Dark Reverse Harem", "Dark Romance"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Insert new trope nodes
    for name in NEW_NODES:
        conn.execute(
            text(
                "INSERT INTO tropes (canonical_name, depth_level, is_root_hub) "
                "VALUES (:name, 0, false) ON CONFLICT (canonical_name) DO NOTHING"
            ),
            {"name": name},
        )

    # 2. Insert parent relationships via cross-join lookup
    for child_name, parent_name in NEW_PARENTS:
        conn.execute(
            text(
                "INSERT INTO trope_parents (trope_uuid, parent_trope_uuid) "
                "SELECT c.trope_uuid, p.trope_uuid "
                "FROM tropes c, tropes p "
                "WHERE c.canonical_name = :child AND p.canonical_name = :parent "
                "ON CONFLICT DO NOTHING"
            ),
            {"child": child_name, "parent": parent_name},
        )

    # 3. Recompute depth_levels for new nodes
    conn.execute(
        text(
            "UPDATE tropes t SET depth_level = ("
            "  SELECT COALESCE(MAX(p.depth_level), 0) + 1 "
            "  FROM trope_parents tp "
            "  JOIN tropes p ON p.trope_uuid = tp.parent_trope_uuid "
            "  WHERE tp.trope_uuid = t.trope_uuid"
            ") WHERE t.canonical_name = ANY(:names)"
        ),
        {"names": NEW_NODES},
    )


def downgrade() -> None:
    pass
