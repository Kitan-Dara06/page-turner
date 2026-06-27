"""Seed v7.0 Sci-Fi taxonomy nodes.

Revision ID: 0013_scifi_taxonomy_v7
Revises: 0012_horror_taxonomy_v6
Create Date: 2026-06-16

Adds 22 Sci-Fi subgenre nodes (First Contact, AI, Post-Apocalyptic, etc.)
"""

from sqlalchemy import text

from alembic import op

revision = "0013_scifi_taxonomy_v7"
down_revision = "0012_horror_taxonomy_v6"
branch_labels = None
depends_on = None

NEW_NODES = [
    "First Contact",
    "Post-Apocalyptic",
    "AI & Consciousness",
    "Generation Ship",
    "Alien Civilization",
    "Time Travel",
    "Parallel Universe",
    "Colony & Terraforming",
    "Near-Future",
    "Far-Future",
    "Biotech Sci-Fi",
    "Space Exploration",
    "Corporate Dystopia",
    "Solarpunk",
    "Cli-Fi",
    "Space Western",
    "Hard Science Thriller",
    "Speculative Philosophical Sci-Fi",
    "Action-Driven Sci-Fi",
    "Biopunk",
    "Uplift",
    "Retrofuturism",
]

NEW_PARENTS = [
    ("First Contact", "Hard Sci-Fi"),
    ("First Contact", "Cosmic/Lovecraftian"),
    ("Post-Apocalyptic", "Future"),
    ("Post-Apocalyptic", "Survival/External"),
    ("AI & Consciousness", "Man vs Technology"),
    ("AI & Consciousness", "Existentialism"),
    ("Generation Ship", "Space Opera"),
    ("Generation Ship", "Survival/External"),
    ("Alien Civilization", "Space Opera"),
    ("Alien Civilization", "Colonialism/Post-Colonialism"),
    ("Time Travel", "Future"),
    ("Time Travel", "Memory & Time"),
    ("Parallel Universe", "Reality"),
    ("Parallel Universe", "Future"),
    ("Colony & Terraforming", "Space Opera"),
    ("Colony & Terraforming", "Survival"),
    ("Near-Future", "Future"),
    ("Near-Future", "Grounded"),
    ("Far-Future", "Future"),
    ("Far-Future", "Epic"),
    ("Biotech Sci-Fi", "Hard Sci-Fi"),
    ("Biotech Sci-Fi", "Body Horror"),
    ("Space Exploration", "Hard Sci-Fi"),
    ("Space Exploration", "Quests"),
    ("Corporate Dystopia", "Dystopia"),
    ("Corporate Dystopia", "Cyberpunk"),
    ("Solarpunk", "Future"),
    ("Solarpunk", "Systemic/Societal Conflict"),
    ("Cli-Fi", "Future"),
    ("Cli-Fi", "Survival/External"),
    ("Space Western", "Space Opera"),
    ("Space Western", "Anti-Hero"),
    ("Hard Science Thriller", "Hard Sci-Fi"),
    ("Hard Science Thriller", "Mysteries"),
    ("Speculative Philosophical Sci-Fi", "Hard Sci-Fi"),
    ("Speculative Philosophical Sci-Fi", "Existentialism"),
    ("Action-Driven Sci-Fi", "Space Opera"),
    ("Action-Driven Sci-Fi", "Military Sci-Fi"),
    ("Biopunk", "Hard Sci-Fi"),
    ("Biopunk", "Body Horror"),
    ("Uplift", "Hard Sci-Fi"),
    ("Uplift", "Systemic/Societal Conflict"),
    ("Retrofuturism", "Future"),
    ("Retrofuturism", "Historical"),
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
