"""Seed v7.1 Sci-Fi refinements.

Revision ID: 0014_scifi_refinements
Revises: 0013_scifi_taxonomy_v7
Create Date: 2026-06-16

Adds 7 Sci-Fi nodes: Biopunk, Uplift, Retrofuturism,
Quantum Sci-Fi, Utopian Sci-Fi, Post-Scarcity Sci-Fi, Totalitarian Sci-Fi
"""

from sqlalchemy import text

from alembic import op

revision = "0014_scifi_refinements"
down_revision = "0013_scifi_taxonomy_v7"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Biopunk",
    "Uplift",
    "Retrofuturism",
    "Quantum Sci-Fi",
    "Utopian Sci-Fi",
    "Post-Scarcity Sci-Fi",
    "Totalitarian Sci-Fi",
]

NEW_PARENTS = [
    ("Biopunk", "Hard Sci-Fi"),
    ("Biopunk", "Body Horror"),
    ("Uplift", "Hard Sci-Fi"),
    ("Uplift", "Systemic/Societal Conflict"),
    ("Retrofuturism", "Future"),
    ("Retrofuturism", "Historical"),
    ("Quantum Sci-Fi", "Hard Sci-Fi"),
    ("Quantum Sci-Fi", "Reality"),
    ("Utopian Sci-Fi", "Future"),
    ("Utopian Sci-Fi", "Systemic/Societal Conflict"),
    ("Post-Scarcity Sci-Fi", "Future"),
    ("Post-Scarcity Sci-Fi", "Utopian Sci-Fi"),
    ("Totalitarian Sci-Fi", "Dystopia"),
    ("Totalitarian Sci-Fi", "Systemic/Societal Conflict"),
]


def upgrade():
    conn = op.get_bind()
    for name in NEW_NODES:
        conn.execute(
            text(
                "INSERT INTO tropes (canonical_name,depth_level,is_root_hub) VALUES (:name,0,false) ON CONFLICT DO NOTHING"
            ),
            {"name": name},
        )
    for c, p in NEW_PARENTS:
        conn.execute(
            text(
                "INSERT INTO trope_parents (trope_uuid,parent_trope_uuid) SELECT c.trope_uuid,p.trope_uuid FROM tropes c,tropes p WHERE c.canonical_name=:c AND p.canonical_name=:p ON CONFLICT DO NOTHING"
            ),
            {"c": c, "p": p},
        )


def downgrade():
    pass
