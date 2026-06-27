"""Seed v3.1 fantasy subgenre refinements.

Revision ID: 0009_fantasy_taxonomy_v31
Revises: 0008_fantasy_taxonomy_v3
Create Date: 2026-06-15

Adds 9 subgenre refinement nodes (Progression, Academy, Military, Political,
Kingdom Building, Monster Hunting, Pirate Fantasy, Time Loop, Magical Competition).
"""

from sqlalchemy import text

from alembic import op

revision = "0009_fantasy_taxonomy_v31"
down_revision = "0008_fantasy_taxonomy_v3"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Progression Fantasy",
    "Academy Fantasy",
    "Military Fantasy",
    "Political Fantasy",
    "Kingdom Building",
    "Monster Hunting",
    "Pirate Fantasy",
    "Time Loop",
    "Magical Competition",
]

NEW_PARENTS = [
    ("Progression Fantasy", "Reality"),
    ("Progression Fantasy", "Quests"),
    ("Academy Fantasy", "Isolated Institution"),
    ("Academy Fantasy", "Reality"),
    ("Military Fantasy", "War & Its Aftermath"),
    ("Military Fantasy", "Epic"),
    ("Political Fantasy", "Court Intrigue"),
    ("Political Fantasy", "Systemic/Societal Conflict"),
    ("Kingdom Building", "Epic"),
    ("Kingdom Building", "Systemic/Societal Conflict"),
    ("Monster Hunting", "Survival/External"),
    ("Monster Hunting", "Quests"),
    ("Pirate Fantasy", "Epic"),
    ("Pirate Fantasy", "Heists"),
    ("Time Loop", "Memory & Time"),
    ("Time Loop", "Reality"),
    ("Magical Competition", "Tournaments/Death Games"),
    ("Magical Competition", "Reality"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name in NEW_NODES:
        conn.execute(
            text(
                "INSERT INTO tropes (canonical_name, depth_level, is_root_hub) "
                "VALUES (:name, 0, false) ON CONFLICT (canonical_name) DO NOTHING"
            ),
            {"name": name},
        )
    for child, parent in NEW_PARENTS:
        conn.execute(
            text(
                "INSERT INTO trope_parents (trope_uuid, parent_trope_uuid) "
                "SELECT c.trope_uuid, p.trope_uuid FROM tropes c, tropes p "
                "WHERE c.canonical_name=:child AND p.canonical_name=:parent "
                "ON CONFLICT DO NOTHING"
            ),
            {"child": child, "parent": parent},
        )


def downgrade() -> None:
    pass
