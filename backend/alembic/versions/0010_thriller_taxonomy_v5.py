"""Seed v5.0 thriller taxonomy nodes.

Revision ID: 0010_thriller_taxonomy_v5
Revises: 0009_fantasy_taxonomy_v31
Create Date: 2026-06-16

Adds 26 thriller nodes — 11 genre registers + 15 trope nodes.
"""

from sqlalchemy import text

from alembic import op

revision = "0010_thriller_taxonomy_v5"
down_revision = "0009_fantasy_taxonomy_v31"
branch_labels = None
depends_on = None

NEW_NODES = [
    "Psychological Thriller",
    "Domestic Thriller",
    "Crime Thriller",
    "Legal Thriller",
    "Spy Thriller",
    "Police Procedural",
    "Serial Killer Thriller",
    "Noir",
    "Political Thriller",
    "Action Thriller",
    "Cozy Mystery",
    "Cat and Mouse",
    "Conspiracy",
    "Race Against Time",
    "Gaslighting",
    "Stalking",
    "Amnesia",
    "Missing Person",
    "Cover-Up",
    "Twist Ending",
    "Everyone Is a Suspect",
    "Red Herring",
    "Cold Case",
    "Vigilante Justice",
    "Wrongfully Accused",
    "Killer POV",
]

NEW_PARENTS = [
    ("Psychological Thriller", "Mysteries"),
    ("Psychological Thriller", "Internal Conflict"),
    ("Domestic Thriller", "Mysteries"),
    ("Domestic Thriller", "Grounded"),
    ("Crime Thriller", "Mysteries"),
    ("Crime Thriller", "Systemic/Societal Conflict"),
    ("Legal Thriller", "Mysteries"),
    ("Legal Thriller", "Systemic/Societal Conflict"),
    ("Spy Thriller", "Mysteries"),
    ("Spy Thriller", "War & Its Aftermath"),
    ("Police Procedural", "Mysteries"),
    ("Police Procedural", "Systemic/Societal Conflict"),
    ("Serial Killer Thriller", "Mysteries"),
    ("Serial Killer Thriller", "Obsession"),
    ("Noir", "Mysteries"),
    ("Noir", "Anti-Hero"),
    ("Political Thriller", "Mysteries"),
    ("Political Thriller", "Corruption of Power"),
    ("Action Thriller", "Mysteries"),
    ("Action Thriller", "Survival"),
    ("Cozy Mystery", "Mysteries"),
    ("Cozy Mystery", "Grounded"),
    ("Cat and Mouse", "Psychological Thriller"),
    ("Cat and Mouse", "Interpersonal Conflict"),
    ("Conspiracy", "Systemic/Societal Conflict"),
    ("Conspiracy", "Political Thriller"),
    ("Race Against Time", "Plot Catalysts & Structures"),
    ("Race Against Time", "Action Thriller"),
    ("Gaslighting", "Internal Conflict"),
    ("Gaslighting", "Psychological Thriller"),
    ("Stalking", "Obsession"),
    ("Stalking", "Psychological Thriller"),
    ("Amnesia", "Memory & Time"),
    ("Amnesia", "Internal Conflict"),
    ("Missing Person", "Mysteries"),
    ("Missing Person", "Grief/Loss"),
    ("Cover-Up", "Systemic/Societal Conflict"),
    ("Cover-Up", "Corruption of Power"),
    ("Twist Ending", "Plot Catalysts & Structures"),
    ("Twist Ending", "Unreliable Narrator"),
    ("Everyone Is a Suspect", "Mysteries"),
    ("Everyone Is a Suspect", "Interpersonal Conflict"),
    ("Red Herring", "Mysteries"),
    ("Red Herring", "Plot Catalysts & Structures"),
    ("Cold Case", "Mysteries"),
    ("Cold Case", "Memory & Time"),
    ("Vigilante Justice", "Anti-Hero"),
    ("Vigilante Justice", "Systemic/Societal Conflict"),
    ("Wrongfully Accused", "Systemic/Societal Conflict"),
    ("Wrongfully Accused", "Survival"),
    ("Killer POV", "Unreliable Narrator"),
    ("Killer POV", "Serial Killer Thriller"),
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
