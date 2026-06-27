"""Seed v8.0 Literary Fiction taxonomy.

Revision ID: 0015_literary_fiction_v8
Revises: 0014_scifi_refinements
Create Date: 2026-06-16

Adds 23 Literary Fiction nodes — genre registers, style, and theme nodes.
"""

from sqlalchemy import text

from alembic import op

revision = "0015_literary_fiction_v8"
down_revision = "0014_scifi_refinements"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Literary Fiction",
    "Autofiction",
    "Postcolonial Literature",
    "Magical Realism Literary",
    "Modernist Literature",
    "Absurdist Fiction",
    "Epistolary Novel",
    "Stream of Consciousness",
    "Campus Novel",
    "Bildungsroman",
    "Family Saga",
    "Immigrant Narrative",
    "War Literature",
    "Protest Literature",
    "Historical Literary Fiction",
    "Experimental Fiction",
    "Literary Noir",
    "Literary Tragedy",
    "Quiet Fiction",
    "Lyrical Prose",
    "Metafiction",
    "Death & Mortality",
    "Alienation & Isolation",
]

NEW_PARENTS = [
    ("Literary Fiction", "Thematic Core"),
    ("Literary Fiction", "Grounded"),
    ("Autofiction", "Literary Fiction"),
    ("Autofiction", "Identity/Self-Discovery"),
    ("Postcolonial Literature", "Literary Fiction"),
    ("Postcolonial Literature", "Colonialism/Post-Colonialism"),
    ("Magical Realism Literary", "Literary Fiction"),
    ("Magical Realism Literary", "Magical Realism"),
    ("Modernist Literature", "Literary Fiction"),
    ("Modernist Literature", "Existentialism"),
    ("Absurdist Fiction", "Literary Fiction"),
    ("Absurdist Fiction", "Existentialism"),
    ("Epistolary Novel", "Literary Fiction"),
    ("Epistolary Novel", "Memory & Time"),
    ("Stream of Consciousness", "Literary Fiction"),
    ("Stream of Consciousness", "Internal Conflict"),
    ("Campus Novel", "Literary Fiction"),
    ("Campus Novel", "Isolated Institution"),
    ("Bildungsroman", "Literary Fiction"),
    ("Bildungsroman", "Identity/Self-Discovery"),
    ("Family Saga", "Literary Fiction"),
    ("Family Saga", "Memory & Time"),
    ("Immigrant Narrative", "Literary Fiction"),
    ("Immigrant Narrative", "Colonialism/Post-Colonialism"),
    ("War Literature", "Literary Fiction"),
    ("War Literature", "War & Its Aftermath"),
    ("Protest Literature", "Literary Fiction"),
    ("Protest Literature", "Systemic/Societal Conflict"),
    ("Historical Literary Fiction", "Literary Fiction"),
    ("Historical Literary Fiction", "Historical"),
    ("Experimental Fiction", "Literary Fiction"),
    ("Literary Noir", "Literary Fiction"),
    ("Literary Noir", "Moral Ambiguity"),
    ("Literary Tragedy", "Literary Fiction"),
    ("Literary Tragedy", "Grief/Loss"),
    ("Quiet Fiction", "Literary Fiction"),
    ("Quiet Fiction", "Existentialism"),
    ("Lyrical Prose", "Literary Fiction"),
    ("Lyrical Prose", "Thematic Core"),
    ("Metafiction", "Literary Fiction"),
    ("Metafiction", "Reality"),
    ("Death & Mortality", "Literary Fiction"),
    ("Death & Mortality", "Grief/Loss"),
    ("Alienation & Isolation", "Literary Fiction"),
    ("Alienation & Isolation", "Internal Conflict"),
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
