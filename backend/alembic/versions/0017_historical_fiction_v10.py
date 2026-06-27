"""Seed v10.0 Historical Fiction taxonomy.

Revision ID: 0017_historical_fiction_v10
Revises: 0016_nonfiction_v9
Create Date: 2026-06-20

Adds 25 Historical Fiction nodes — 2 setting-period nodes + 23 genre registers.
Fixed Epic overloading: scale signal via Epic (Scale), period via Ancient/Medieval World (Timeline).
"""

from sqlalchemy import text

from alembic import op

revision = "0017_historical_fiction_v10"
down_revision = "0016_nonfiction_v9"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Ancient World",
    "Medieval World",
    "Historical Fiction",
    "Ancient Historical Fiction",
    "Medieval Historical Fiction",
    "Victorian Fiction",
    "Historical Epic",
    "Historical Mystery",
    "Historical Thriller",
    "Historical Adventure",
    "War Fiction",
    "Biographical Fiction",
    "Alternate History Fiction",
    "Gaslamp Fiction",
    "Colonial Historical Fiction",
    "Postcolonial Historical Fiction",
    "Rural Historical Fiction",
    "Western Fiction",
    "Historical Bildungsroman",
    "Political Historical Fiction",
    "Experimental Historical Fiction",
    "African Historical Fiction",
    "Asian Historical Fiction",
    "European Historical Fiction",
    "Middle Eastern Historical Fiction",
]

NEW_PARENTS = [
    # Setting-period nodes
    ("Ancient World", "Timeline"),
    ("Medieval World", "Timeline"),
    # Genre registers — by period
    ("Historical Fiction", "Literary Fiction"),
    ("Historical Fiction", "Historical"),
    ("Ancient Historical Fiction", "Historical Fiction"),
    ("Ancient Historical Fiction", "Ancient World"),
    ("Medieval Historical Fiction", "Historical Fiction"),
    ("Medieval Historical Fiction", "Medieval World"),
    ("Victorian Fiction", "Historical Fiction"),
    ("Victorian Fiction", "Gothic Horror"),
    # By form/style — Epic = scale only
    ("Historical Epic", "Historical Fiction"),
    ("Historical Epic", "Epic"),
    ("Historical Mystery", "Historical Fiction"),
    ("Historical Mystery", "Mysteries"),
    ("Historical Thriller", "Historical Fiction"),
    ("Historical Thriller", "Psychological Horror"),
    ("Historical Adventure", "Historical Fiction"),
    ("Historical Adventure", "Quests"),
    ("War Fiction", "Historical Fiction"),
    ("War Fiction", "War & Its Aftermath"),
    ("Biographical Fiction", "Historical Fiction"),
    ("Biographical Fiction", "Literary Fiction"),
    ("Alternate History Fiction", "Historical Fiction"),
    ("Alternate History Fiction", "Alternate History"),
    ("Gaslamp Fiction", "Historical Fiction"),
    ("Gaslamp Fiction", "Gaslamp Fantasy"),
    # Cross-genre registers
    ("Colonial Historical Fiction", "Historical Fiction"),
    ("Colonial Historical Fiction", "Colonialism/Post-Colonialism"),
    ("Postcolonial Historical Fiction", "Historical Fiction"),
    ("Postcolonial Historical Fiction", "Colonialism/Post-Colonialism"),
    ("Rural Historical Fiction", "Historical Fiction"),
    ("Rural Historical Fiction", "Class Struggle"),
    ("Western Fiction", "Historical Fiction"),
    ("Western Fiction", "Survival/External"),
    ("Historical Bildungsroman", "Historical Fiction"),
    ("Historical Bildungsroman", "Bildungsroman"),
    ("Political Historical Fiction", "Historical Fiction"),
    ("Political Historical Fiction", "Systemic/Societal Conflict"),
    ("Experimental Historical Fiction", "Historical Fiction"),
    ("Experimental Historical Fiction", "Experimental Fiction"),
    # Regional registers — single-parent for clean geo signal
    ("African Historical Fiction", "Historical Fiction"),
    ("Asian Historical Fiction", "Historical Fiction"),
    ("European Historical Fiction", "Historical Fiction"),
    ("Middle Eastern Historical Fiction", "Historical Fiction"),
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
