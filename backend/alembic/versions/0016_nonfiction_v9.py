"""Seed v9.0 Non-Fiction taxonomy.

Revision ID: 0016_nonfiction_v9
Revises: 0015_literary_fiction_v8
Create Date: 2026-06-16

Adds 22 Non-Fiction nodes — Memoir, Narrative Nonfiction, True Crime, etc.
Also adds dual parent path for Autofiction (Literary + Memoir).
"""

from sqlalchemy import text

from alembic import op

revision = "0016_nonfiction_v9"
down_revision = "0015_literary_fiction_v8"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Nonfiction",
    "Narrative Nonfiction",
    "Non-Narrative Nonfiction",
    "Memoir",
    "Autobiography",
    "True Crime Narrative",
    "Investigative Journalism",
    "Travel Writing",
    "Nature Writing",
    "War Memoir",
    "Essays",
    "Literary Journalism",
    "History",
    "Philosophy",
    "Popular Science",
    "Self-Help",
    "Biography",
    "Psychology",
    "Sociology",
    "Economics",
    "Political Theory",
    "Cultural Criticism",
]

NEW_PARENTS = [
    ("Nonfiction", "Thematic Core"),
    ("Nonfiction", "Grounded"),
    ("Narrative Nonfiction", "Nonfiction"),
    ("Narrative Nonfiction", "Grounded"),
    ("Non-Narrative Nonfiction", "Nonfiction"),
    ("Memoir", "Narrative Nonfiction"),
    ("Memoir", "Identity/Self-Discovery"),
    ("Autobiography", "Memoir"),
    ("True Crime Narrative", "Narrative Nonfiction"),
    ("True Crime Narrative", "Mysteries"),
    ("Investigative Journalism", "Narrative Nonfiction"),
    ("Investigative Journalism", "Systemic/Societal Conflict"),
    ("Travel Writing", "Narrative Nonfiction"),
    ("Travel Writing", "Quests"),
    ("Nature Writing", "Narrative Nonfiction"),
    ("Nature Writing", "Survival/External"),
    ("War Memoir", "Memoir"),
    ("War Memoir", "War & Its Aftermath"),
    ("Essays", "Narrative Nonfiction"),
    ("Essays", "Thematic Core"),
    ("Literary Journalism", "Investigative Journalism"),
    ("Literary Journalism", "Essays"),
    ("History", "Non-Narrative Nonfiction"),
    ("History", "War & Its Aftermath"),
    ("Philosophy", "Non-Narrative Nonfiction"),
    ("Philosophy", "Existentialism"),
    ("Popular Science", "Non-Narrative Nonfiction"),
    ("Popular Science", "Hard Sci-Fi"),
    ("Self-Help", "Non-Narrative Nonfiction"),
    ("Self-Help", "Identity/Self-Discovery"),
    ("Biography", "Narrative Nonfiction"),
    ("Biography", "Non-Narrative Nonfiction"),
    ("Psychology", "Non-Narrative Nonfiction"),
    ("Psychology", "Internal Conflict"),
    ("Sociology", "Non-Narrative Nonfiction"),
    ("Sociology", "Systemic/Societal Conflict"),
    ("Economics", "Non-Narrative Nonfiction"),
    ("Economics", "Class Struggle"),
    ("Political Theory", "Non-Narrative Nonfiction"),
    ("Political Theory", "Systemic/Societal Conflict"),
    ("Cultural Criticism", "Non-Narrative Nonfiction"),
    ("Cultural Criticism", "Thematic Core"),
    # Autofiction dual parent — Memoir path
    ("Autofiction", "Literary Fiction"),
    ("Autofiction", "Identity/Self-Discovery"),
    ("Autofiction", "Memoir"),
    ("Autofiction", "Identity/Self-Discovery"),
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
