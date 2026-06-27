"""Add structure/tone/emotion axes to taxonomy.

Revision ID: 0011_axes_v51
Revises: 0010_thriller_taxonomy_v5
Create Date: 2026-06-16

Adds 16 cross-genre nodes: 6 structural archetypes, 5 tone nodes, 5 emotional drivers.
These give the LLM extraction prompt the vocabulary to tag books with dimensions
that readers actually use: structure feel, tonal register, and emotional payoff.
"""

from sqlalchemy import text

from alembic import op

revision = "0011_axes_v51"
down_revision = "0010_thriller_taxonomy_v5"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Dual Timeline",
    "Single POV",
    "Multi-POV Structure",
    "Epistolary",
    "Reverse Timeline",
    "Nonlinear Narrative",
    "Dark Tone",
    "Light Tone",
    "Stylized",
    "Mind-Bending",
    "Cold/Clinical",
    "Paranoia",
    "Guilt",
    "Revenge",
    "Fear of Exposure",
    "Moral Ambiguity",
]

NEW_PARENTS = [
    ("Dual Timeline", "Plot Catalysts & Structures"),
    ("Dual Timeline", "Memory & Time"),
    ("Single POV", "Plot Catalysts & Structures"),
    ("Single POV", "Internal Conflict"),
    ("Multi-POV Structure", "Plot Catalysts & Structures"),
    ("Multi-POV Structure", "Interpersonal Conflict"),
    ("Epistolary", "Plot Catalysts & Structures"),
    ("Epistolary", "Memory & Time"),
    ("Reverse Timeline", "Plot Catalysts & Structures"),
    ("Reverse Timeline", "Memory & Time"),
    ("Nonlinear Narrative", "Plot Catalysts & Structures"),
    ("Nonlinear Narrative", "Memory & Time"),
    ("Dark Tone", "Thematic Core"),
    ("Dark Tone", "Internal Conflict"),
    ("Light Tone", "Thematic Core"),
    ("Light Tone", "Grounded"),
    ("Stylized", "Reality"),
    ("Stylized", "Thematic Core"),
    ("Mind-Bending", "Reality"),
    ("Mind-Bending", "Internal Conflict"),
    ("Cold/Clinical", "Thematic Core"),
    ("Cold/Clinical", "Unreliable Narrator"),
    ("Paranoia", "Internal Conflict"),
    ("Paranoia", "Psychological Thriller"),
    ("Guilt", "Internal Conflict"),
    ("Guilt", "Grief/Loss"),
    ("Revenge", "Internal Conflict"),
    ("Revenge", "Systemic/Societal Conflict"),
    ("Fear of Exposure", "Internal Conflict"),
    ("Fear of Exposure", "Psychological Thriller"),
    ("Moral Ambiguity", "Anti-Hero"),
    ("Moral Ambiguity", "Internal Conflict"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for name in NEW_NODES:
        conn.execute(
            text(
                "INSERT INTO tropes (canonical_name,depth_level,is_root_hub) "
                "VALUES (:name,0,false) ON CONFLICT (canonical_name) DO NOTHING"
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
