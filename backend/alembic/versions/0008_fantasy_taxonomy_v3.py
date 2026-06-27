"""Seed v3.0 fantasy taxonomy nodes.

Revision ID: 0008_fantasy_taxonomy_v3
Revises: 0007_romance_taxonomy_v2
Create Date: 2026-06-15

Adds 22 new trope nodes for fantasy genre registers and plot/character tropes.
"""

from sqlalchemy import text

from alembic import op

revision = "0008_fantasy_taxonomy_v3"
down_revision = "0007_romance_taxonomy_v2"
branch_labels = None
depends_on = None

NEW_NODES = [
    "High Fantasy",
    "Urban Fantasy",
    "Low Fantasy",
    "Dark Fantasy",
    "Grimdark",
    "Cozy Fantasy",
    "Romantasy",
    "Fairy Tale Retelling",
    "Sword & Sorcery",
    "Gaslamp Fantasy",
    "Science Fantasy",
    "Wuxia",
    "Court Intrigue",
    "Secret Heir",
    "Reluctant Hero",
    "Ancient Evil",
    "Reincarnation",
    "Forced Alliance",
    "Prophecy",
    "Gods and Mortals",
    "Rivals to Lovers",
    "Band of Misfits",
    "Fae Courts",
    "Dragon Riders",
]

NEW_PARENTS = [
    ("High Fantasy", "Epic"),
    ("High Fantasy", "Reality"),
    ("Urban Fantasy", "Reality"),
    ("Urban Fantasy", "Grounded"),
    ("Low Fantasy", "Reality"),
    ("Low Fantasy", "Grounded"),
    ("Dark Fantasy", "Reality"),
    ("Dark Fantasy", "Obsession"),
    ("Grimdark", "Dark Fantasy"),
    ("Grimdark", "War & Its Aftermath"),
    ("Cozy Fantasy", "Reality"),
    ("Cozy Fantasy", "Found Family Formation"),
    ("Romantasy", "Reality"),
    ("Romantasy", "Relationship Dynamics"),
    ("Fairy Tale Retelling", "Reality"),
    ("Fairy Tale Retelling", "Historical"),
    ("Sword & Sorcery", "Epic"),
    ("Sword & Sorcery", "Anti-Hero"),
    ("Gaslamp Fantasy", "Historical"),
    ("Gaslamp Fantasy", "Reality"),
    ("Science Fantasy", "Reality"),
    ("Science Fantasy", "Hard Sci-Fi"),
    ("Wuxia", "Historical"),
    ("Wuxia", "Epic"),
    ("Court Intrigue", "Systemic/Societal Conflict"),
    ("Court Intrigue", "Quests"),
    ("Secret Heir", "Chosen One"),
    ("Secret Heir", "Court Intrigue"),
    ("Reluctant Hero", "Chosen One"),
    ("Reluctant Hero", "Internal Conflict"),
    ("Ancient Evil", "Cosmic/Lovecraftian"),
    ("Ancient Evil", "Plot Catalysts & Structures"),
    ("Reincarnation", "Memory & Time"),
    ("Reincarnation", "Reality"),
    ("Forced Alliance", "Interpersonal Conflict"),
    ("Forced Alliance", "Plot Catalysts & Structures"),
    ("Prophecy", "Chosen One"),
    ("Prophecy", "Plot Catalysts & Structures"),
    ("Gods and Mortals", "Cosmic/Lovecraftian"),
    ("Gods and Mortals", "Thematic Core"),
    ("Rivals to Lovers", "Enemies to Lovers"),
    ("Rivals to Lovers", "Relationship Dynamics"),
    ("Band of Misfits", "Found Family Formation"),
    ("Band of Misfits", "Anti-Hero"),
    ("Fae Courts", "Court Intrigue"),
    ("Fae Courts", "Reality"),
    ("Dragon Riders", "Epic"),
    ("Dragon Riders", "Quests"),
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
