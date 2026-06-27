"""Seed v11.0 Mystery Fiction + Nonfiction/Memoir refinements.

Revision ID: 0018_mystery_nonfiction_v11
Revises: 0017_historical_fiction_v10
Create Date: 2026-06-20

Adds Mystery Fiction genre register anchor + 12 mystery subgenre nodes.
Adds 10 memoir/biography refinements + 2 concept nodes.
Reparents Cozy Mystery and Historical Mystery under Mystery Fiction.
"""

from sqlalchemy import text

from alembic import op

revision = "0018_mystery_nonfiction_v11"
down_revision = "0017_historical_fiction_v10"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Crime",
    "Mystery Fiction",
    "Amateur Sleuth",
    "Hardboiled Detective",
    "Classic Detective Fiction",
    "Nordic Noir",
    "Psychological Mystery",
    "Techno-Mystery",
    "Small Town Mystery",
    "Domestic Cozy Mystery",
    "Animal Cozy Mystery",
    "Courtroom Mystery",
    "Puzzle Mystery",
    "Coming of Age Memoir",
    "Trauma Memoir",
    "Political Memoir",
    "Creative Nonfiction",
    "Celebrity Biography",
    "Literary Biography",
    "Investigative Nonfiction",
    "True Crime",
    "Scientific Memoir",
]

NEW_PARENTS = [
    # Concept node
    ("Crime", "Thematic Core"),
    # Mystery Fiction genre register anchor
    ("Mystery Fiction", "Mysteries"),
    ("Mystery Fiction", "Grounded"),
    # Mystery subgenre registers
    ("Amateur Sleuth", "Mystery Fiction"),
    ("Amateur Sleuth", "Whodunit"),
    ("Hardboiled Detective", "Mystery Fiction"),
    ("Hardboiled Detective", "Anti-Hero"),
    ("Classic Detective Fiction", "Mystery Fiction"),
    ("Classic Detective Fiction", "Whodunit"),
    ("Nordic Noir", "Mystery Fiction"),
    ("Nordic Noir", "Psychological Horror"),
    ("Psychological Mystery", "Mystery Fiction"),
    ("Psychological Mystery", "Psychological Thriller"),
    ("Techno-Mystery", "Mystery Fiction"),
    ("Techno-Mystery", "Man vs Technology"),
    ("Small Town Mystery", "Cozy Mystery"),
    ("Domestic Cozy Mystery", "Cozy Mystery"),
    ("Domestic Cozy Mystery", "Domestic Thriller"),
    ("Animal Cozy Mystery", "Cozy Mystery"),
    ("Courtroom Mystery", "Legal Thriller"),
    ("Courtroom Mystery", "Whodunit"),
    ("Puzzle Mystery", "Whodunit"),
    # Memoir / Biography refinements
    ("Coming of Age Memoir", "Memoir"),
    ("Coming of Age Memoir", "Bildungsroman"),
    ("Trauma Memoir", "Memoir"),
    ("Trauma Memoir", "Grief/Loss"),
    ("Political Memoir", "Memoir"),
    ("Political Memoir", "Systemic/Societal Conflict"),
    ("Creative Nonfiction", "Memoir"),
    ("Creative Nonfiction", "Literary Fiction"),
    ("Celebrity Biography", "Biography"),
    ("Literary Biography", "Biography"),
    ("Literary Biography", "Literary Fiction"),
    ("Investigative Nonfiction", "Narrative Nonfiction"),
    ("Investigative Nonfiction", "Systemic/Societal Conflict"),
    ("True Crime", "Narrative Nonfiction"),
    ("True Crime", "Mysteries"),
    ("Scientific Memoir", "Memoir"),
    ("Scientific Memoir", "Popular Science"),
    # Reparents — add Mystery Fiction parent to existing nodes
    ("Cozy Mystery", "Mystery Fiction"),
    ("Historical Mystery", "Mystery Fiction"),
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
