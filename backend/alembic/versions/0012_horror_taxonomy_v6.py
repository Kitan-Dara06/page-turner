"""Seed v6.0 horror subgenre registers.

Revision ID: 0012_horror_taxonomy_v6
Revises: 0011_axes_v51
Create Date: 2026-06-16

Adds 7 horror subgenre nodes (Gothic, Supernatural, Haunted House,
Weird Fiction, Quiet Horror, Domestic Horror, Dread & Atmosphere).
"""

from sqlalchemy import text

from alembic import op

revision = "0012_horror_taxonomy_v6"
down_revision = "0011_axes_v51"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Gothic Horror",
    "Supernatural Horror",
    "Haunted House",
    "Weird Fiction",
    "Quiet Horror",
    "Domestic Horror",
    "Dread & Atmosphere",
]

NEW_PARENTS = [
    ("Gothic Horror", "Psychological Horror"),
    ("Gothic Horror", "Historical"),
    ("Supernatural Horror", "Reality"),
    ("Supernatural Horror", "Cosmic/Lovecraftian"),
    ("Haunted House", "Isolated Institution"),
    ("Haunted House", "Supernatural Horror"),
    ("Weird Fiction", "Cosmic/Lovecraftian"),
    ("Weird Fiction", "Reality"),
    ("Quiet Horror", "Psychological Horror"),
    ("Quiet Horror", "Existentialism"),
    ("Domestic Horror", "Psychological Horror"),
    ("Domestic Horror", "Interpersonal Conflict"),
    ("Dread & Atmosphere", "Psychological Horror"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name in NEW_NODES:
        conn.execute(
            text(
                "INSERT INTO tropes (canonical_name,depth_level,is_root_hub) "
                "VALUES (:name,0,false) ON CONFLICT DO NOTHING"
            ),
            {"name": name},
        )
    for child, parent in NEW_PARENTS:
        conn.execute(
            text(
                "INSERT INTO trope_parents (trope_uuid,parent_trope_uuid) "
                "SELECT c.trope_uuid,p.trope_uuid FROM tropes c,tropes p "
                "WHERE c.canonical_name=:child AND p.canonical_name=:parent "
                "ON CONFLICT DO NOTHING"
            ),
            {"child": child, "parent": parent},
        )


def downgrade() -> None:
    pass
