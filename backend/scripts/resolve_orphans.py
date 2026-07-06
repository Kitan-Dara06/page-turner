"""
Batch-resolve high-frequency orphans.
Run: .venv/bin/python scripts/resolve_orphans.py [--dry-run]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

from app.db.session import SessionLocal

DRY_RUN = "--dry-run" in sys.argv

CASING_MAPS = {
    # ── Genre → Canonical
    "dark romance": "Dark Romance",
    "historical romance": "Historical Romance",
    "contemporary romance": "Contemporary Romance",
    "science fiction": "Hard Sci-Fi",
    "fantasy": "High Fantasy",
    "thriller": "Psychological Thriller",
    "horror": "Psychological Horror",
    "memoir": "Memoir",
    "literary fiction": "Literary Fiction",
    "psychological horror": "Psychological Horror",
    "urban fantasy": "Urban Fantasy",
    "gothic": "Gothic Horror",
    "young adult fiction": "Bildungsroman",
    "coming of age": "Bildungsroman",
    "coming-of-age": "Bildungsroman",
    "southern gothic": "Gothic Horror",
    "class struggle": "Class Struggle",
    "true crime": "True Crime",
    "time travel": "Time Travel",
    "post-apocalyptic": "Post-Apocalyptic",
    "vampire": "Supernatural Horror",
    "vampires": "Supernatural Horror",
    "enemies to lovers": "Enemies to Lovers",
    "friends to lovers": "Friends to Lovers",
    "fake dating": "Fake Dating",
    "love triangle": "Love Triangle",
    "second chance": "Second Chance Romance",
    "age gap": "Age Gap Romance",
    "slow burn": "Slow Burn",
    "reverse harem": "Reverse Harem",
    "fated mates": "Romantic Fantasy",
    "forced proximity": "Forced Proximity",
    "arranged marriage": "Romantic Fantasy",
    "college romance": "Romantic Fantasy",
    "college students": "Campus Novel",
    "bdsm": "Dark Romance",
    "motorcycle club": "Dark Romance",
    "betrayal": "Corruption of Power",
    "deception": "Corruption of Power",
    "murder mystery": "Mysteries",
    "police procedural": "Police Procedural",
    "political intrigue": "Political Thriller",
    "allegory": "Absurdist Fiction",
    "first contact": "First Contact",
    "social commentary": "Protest Literature",
    "road trip": "Travel Writing",
    "adventure": "Quests",
    "curse": "Supernatural Horror",
    "cult": "Isolated Institution",
    "madness": "Psychological Horror",
    "secrets": "Red Herring",
    "revenge": "Vigilante Justice",
    "vengeance": "Vigilante Justice",
    "guilt": "Internal Conflict",
    "death": "Grief/Loss",
    "grief/loss": "Grief/Loss",
    "addiction": "Internal Conflict",
    "depression": "Internal Conflict",
    "trauma": "Grief/Loss",
    "assault": "Systemic/Societal Conflict",
    "abuse": "Systemic/Societal Conflict",
    "torture": "Psychological Horror",
    "kidnapping": "Missing Person",
    "motherhood": "Family Saga",
    "family secrets": "Family Saga",
    "suspense": "Psychological Thriller",
    "suspenseful": "Psychological Thriller",
    "mysterious": "Mysteries",
    "challenging": "Thematic Core",
    "inspiring": "Identity/Self-Discovery",
    "hopeful": "Redemption Arc",
    "reflective": "Memory & Time",
    "witty": "Light Tone",
    "dramatic": "Dark Tone",
    "adventurous": "Quests",
    "faith": "Thematic Core",
    "art": "Thematic Core",
    "history": "Historical",
    "magic": "Magical Realism",
    "dragons": "Dragon Riders",
    "small town": "Small Town Romance",
    "dark": "Dark Tone",
    "emotional": "Emotional Intensity",
    "sad": "Emotional Intensity",
    "tense": "Psychological Thriller",
    "romantic": "Relationship Dynamics",
    "humor": "Humorous Tone",
    "satire": "Satire",
    "sequel": "Second Chance Romance",
    "rivalry": "Internal Conflict",
    "jealousy": "Internal Conflict",
    "first love": "Bildungsroman",
    "unreliable narrator": "Memory & Time",
    "standalone": "Romantic Fantasy",
    "romantasy": "Romantic Fantasy",
    "twist ending": "Red Herring",
    "autobiography": "Memoir",
    "philosophy": "Thematic Core",
    "atmospheric": "Dark Tone",
    "19th century": "Historical",
    "gore": "Psychological Horror",
    "religion": "Thematic Core",
    "adultery": "Internal Conflict",
    "aging": "Grief/Loss",
    "grimdark": "Dark Tone",
    # Production-specific orphans that map to existing tropes
    "violence": "Psychological Horror",
    "young adult": "Bildungsroman",
    "contemporary": "Contemporary Romance",
    "romance": "Relationship Dynamics",
    "mysteries": "Mysteries",
    "american": "Travel Writing",
    "mythological retelling": "Mythology",
    "social critique": "Protest Literature",
    "redemption arc": "Redemption Arc",
    "hacker": "Hacking & Cyber",
}

PROMOTE_NODES = {
    "funny": "Humorous Tone",
    "steamy": "Steamy Romance",
    "spicy": "Steamy Romance",
    "graphic": "Graphic Content",
    "explicit": "Explicit Content",
    # New literary nodes
    "dark academia": "Dark Academia",
    "marriage of convenience": "Marriage of Convenience",
    "sports romance": "Sports Romance",
    "paranormal romance": "Paranormal Romance",
    "omegaverse": "Omegaverse",
    "why choose": "Why Choose",
    "wallflower": "Wallflower",
    "possessive hero": "Possessive Hero",
    "rural setting": "Rural Setting",
    "artists": "Artist Protagonist",
    "fable": "Fable",
    "magician": "Magician",
    "hacking": "Hacking & Cyber",
    "adventure stories": "Quest Narrative",
    "exploration": "Discovery Narrative",
    "friendship": "Found Family",
    "slavery": "Enslavement",
    # Production-specific orphans (2026-07-06)
    "emotional": "Emotional Intensity",
    "sad": "Emotional Intensity",
    "lighthearted": "Light Tone",
    "fae": "Fae & Faerie",
    "mythology": "Mythology",
    "stoicism": "Emotional Intensity",
    "family drama": "Family Saga",
    "philosophical": "Thematic Core",
    "poverty": "Class Struggle",
    "zombies": "Zombie Fiction",
    "feminist": "Protest Literature",
    "science": "Science Writing",
    "retelling": "Retelling",
    "neurosurgeon": "Medical Drama",
    "billionaire romance": "Romantic Fantasy",
    "diplomacy": "Political Thriller",
    "metaphysics": "Thematic Core",
    "action-packed": "Action & Adventure",
    "non-fiction": "Nonfiction Narrative",
    "solitude": "Internal Conflict",
    "ghost story": "Gothic Horror",
    "historical fiction": "Historical",
    "paranoia": "Psychological Thriller",
    "journalist": "Investigative Thriller",
    "empathy": "Thematic Core",
    "apocalypse": "Post-Apocalyptic",
    "office romance": "Forced Proximity",
    "romantic comedy": "Light Tone",
    "trilogy": "Romantic Fantasy",
    "jazz age": "Historical",
    "supernatural horror": "Supernatural Horror",
    "fake relationship": "Fake Dating",
    "cult classic": "Cult & Counterculture",
}


def resolve(db):
    mapped = promoted = 0
    tropes = {
        r[0].lower(): r[1]
        for r in db.execute(text("SELECT canonical_name, trope_uuid FROM tropes")).all()
    }

    for tag_text, canonical in CASING_MAPS.items():
        trope_uuid = tropes.get(canonical.lower())
        if not trope_uuid:
            continue
        row = db.execute(
            text("SELECT frequency_count FROM orphan_queue WHERE tag_text = :tag"),
            {"tag": tag_text},
        ).fetchone()
        if not row:
            continue
        freq = row[0]
        if DRY_RUN:
            print(f"  MAP  {tag_text} ({freq}) → {canonical}")
        else:
            db.execute(
                text("DELETE FROM orphan_queue WHERE tag_text = :tag"),
                {"tag": tag_text},
            )
            db.execute(
                text(
                    "INSERT INTO trope_aliases (trope_uuid, alias_text, source) "
                    "VALUES (:uuid, :alias, 'orphan_mapped') ON CONFLICT DO NOTHING"
                ),
                {"uuid": trope_uuid, "alias": tag_text},
            )
        mapped += 1

    for tag_text, canonical_name in PROMOTE_NODES.items():
        existing_uuid = tropes.get(canonical_name.lower())
        row = db.execute(
            text("SELECT frequency_count FROM orphan_queue WHERE tag_text = :tag"),
            {"tag": tag_text},
        ).fetchone()
        if not row:
            continue
        freq = row[0]
        if DRY_RUN:
            if existing_uuid:
                print(f"  MAP  {tag_text} ({freq}) → {canonical_name} (exists)")
            else:
                print(f"  PROMOTE {tag_text} ({freq}) → {canonical_name}")
        else:
            if existing_uuid:
                # Node already exists — map the orphan to it instead
                db.execute(
                    text("DELETE FROM orphan_queue WHERE tag_text = :tag"),
                    {"tag": tag_text},
                )
                db.execute(
                    text(
                        "INSERT INTO trope_aliases (trope_uuid, alias_text, source) "
                        "VALUES (:uuid, :alias, 'orphan_mapped') ON CONFLICT DO NOTHING"
                    ),
                    {"uuid": existing_uuid, "alias": tag_text},
                )
            else:
                new_uuid = db.execute(
                    text(
                        "INSERT INTO tropes (canonical_name, depth_level, is_root_hub) "
                        "VALUES (:name, 0, false) ON CONFLICT (canonical_name) DO NOTHING "
                        "RETURNING trope_uuid"
                    ),
                    {"name": canonical_name},
                ).scalar()
                if new_uuid is None:
                    # Race: another process created it between our check and insert
                    new_uuid = tropes.get(canonical_name.lower())
                    if not new_uuid:
                        continue
                db.execute(
                    text(
                        "INSERT INTO trope_aliases (trope_uuid, alias_text, source) "
                        "VALUES (:uuid, :alias, 'orphan_promoted')"
                    ),
                    {"uuid": new_uuid, "alias": tag_text},
                )
                db.execute(
                    text("DELETE FROM orphan_queue WHERE tag_text = :tag"),
                    {"tag": tag_text},
                )
        promoted += 1

    if not DRY_RUN:
        db.commit()
    print(f"\nDone. mapped={mapped} promoted={promoted}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        resolve(db)
    finally:
        db.close()
