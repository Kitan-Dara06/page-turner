"""Seed Catalog Script
Runs full enrichment pipeline per book. Skips already-completed books.
Stops on 8 consecutive Google Books failures.
Run: PYTHONPATH=$PWD .venv/bin/python scripts/seed_catalog.py
"""

import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func as sf
from sqlalchemy import select

import app.models  # noqa: F401
from app.db.session import SessionLocal
from app.models.books import Work
from app.models.enrichment import EnrichmentCache

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # quiet HTTP logs

FLASHCARD_POOL = [
    ("The Name of the Wind", "Patrick Rothfuss"),
    ("A Game of Thrones", "George R.R. Martin"),
    ("The Hobbit", "J.R.R. Tolkien"),
    ("Mistborn: The Final Empire", "Brandon Sanderson"),
    ("The Fifth Season", "N.K. Jemisin"),
    ("The Lies of Locke Lamora", "Scott Lynch"),
    ("Assassin's Apprentice", "Robin Hobb"),
    ("The Priory of the Orange Tree", "Samantha Shannon"),
    ("Jonathan Strange & Mr Norrell", "Susanna Clarke"),
    ("The Blade Itself", "Joe Abercrombie"),
    ("Circe", "Madeline Miller"),
    ("The Night Circus", "Erin Morgenstern"),
    ("Uprooted", "Naomi Novik"),
    ("The Bear and the Nightingale", "Katherine Arden"),
    ("The Queen of Nothing", "Holly Black"),
    ("Six of Crows", "Leigh Bardugo"),
    ("The House in the Cerulean Sea", "TJ Klune"),
    ("Dune", "Frank Herbert"),
    ("Project Hail Mary", "Andy Weir"),
    ("Neuromancer", "William Gibson"),
    ("The Left Hand of Darkness", "Ursula K. Le Guin"),
    ("Hyperion", "Dan Simmons"),
    ("Snow Crash", "Neal Stephenson"),
    ("The Three-Body Problem", "Cixin Liu"),
    ("Children of Time", "Adrian Tchaikovsky"),
    ("Ancillary Justice", "Ann Leckie"),
    ("A Memory Called Empire", "Arkady Martine"),
    ("Klara and the Sun", "Kazuo Ishiguro"),
    ("The Murderbot Diaries: All Systems Red", "Martha Wells"),
    ("Blindsight", "Peter Watts"),
    ("The Dispossessed", "Ursula K. Le Guin"),
    ("Altered Carbon", "Richard K. Morgan"),
    ("The Hunger Games", "Suzanne Collins"),
    ("Red Rising", "Pierce Brown"),
    ("The Stranger", "Albert Camus"),
    ("1984", "George Orwell"),
    ("Beloved", "Toni Morrison"),
    ("The Great Gatsby", "F. Scott Fitzgerald"),
    ("Crime and Punishment", "Fyodor Dostoevsky"),
    ("One Hundred Years of Solitude", "Gabriel Garcia Marquez"),
    ("The Road", "Cormac McCarthy"),
    ("Never Let Me Go", "Kazuo Ishiguro"),
    ("The Handmaid's Tale", "Margaret Atwood"),
    ("A Little Life", "Hanya Yanagihara"),
    ("The Secret History", "Donna Tartt"),
    ("White Teeth", "Zadie Smith"),
    ("The Goldfinch", "Donna Tartt"),
    ("Piranesi", "Susanna Clarke"),
    ("Normal People", "Sally Rooney"),
    ("The Vegetarian", "Han Kang"),
    ("Things Fall Apart", "Chinua Achebe"),
    ("Giovanni's Room", "James Baldwin"),
    ("The Grapes of Wrath", "John Steinbeck"),
    ("The Power", "Naomi Alderman"),
    ("The Time Traveler's Wife", "Audrey Niffenegger"),
    ("All Quiet on the Western Front", "Erich Maria Remarque"),
    ("The Girl with the Dragon Tattoo", "Stieg Larsson"),
    ("Gone Girl", "Gillian Flynn"),
    ("The Silent Patient", "Alex Michaelides"),
    ("And Then There Were None", "Agatha Christie"),
    ("The Big Sleep", "Raymond Chandler"),
    ("The Hound of the Baskervilles", "Arthur Conan Doyle"),
    ("The Girl on the Train", "Paula Hawkins"),
    ("Sharp Objects", "Gillian Flynn"),
    ("The Da Vinci Code", "Dan Brown"),
    ("Rebecca", "Daphne du Maurier"),
    ("Pride and Prejudice", "Jane Austen"),
    ("Outlander", "Diana Gabaldon"),
    ("The Love Hypothesis", "Ali Hazelwood"),
    ("Red, White & Royal Blue", "Casey McQuiston"),
    ("Beach Read", "Emily Henry"),
    ("The Hating Game", "Sally Thorne"),
    ("Haunting Adeline", "H.D. Carlton"),
    ("The Spanish Love Deception", "Elena Armas"),
    ("Twilight", "Stephenie Meyer"),
    ("The Kiss Quotient", "Helen Hoang"),
    ("Credence", "Penelope Douglas"),
    ("The Song of Achilles", "Madeline Miller"),
    ("Love, Theoretically", "Ali Hazelwood"),
    ("The Bronze Horseman", "Paullina Simons"),
    ("A Court of Thorns and Roses", "Sarah J. Maas"),
    ("The Shining", "Stephen King"),
    ("House of Leaves", "Mark Z. Danielewski"),
    ("Mexican Gothic", "Silvia Moreno-Garcia"),
    ("The Haunting of Hill House", "Shirley Jackson"),
    ("Bird Box", "Josh Malerman"),
    ("Our Share of Night", "Mariana Enriquez"),
    ("Between Two Fires", "Christopher Buehlman"),
    ("Sapiens", "Yuval Noah Harari"),
    ("Meditations", "Marcus Aurelius"),
    ("Thinking, Fast and Slow", "Daniel Kahneman"),
    ("The Will to Change", "bell hooks"),
    ("In Cold Blood", "Truman Capote"),
    ("Educated", "Tara Westover"),
    ("The Pillars of the Earth", "Ken Follett"),
]

_seen_titles = {t.lower() for t, _ in FLASHCARD_POOL}

try:
    from app.taxonomy.romance_seed_data import ROMANCE_SEED_BOOKS

    _r = []
    for g, b in ROMANCE_SEED_BOOKS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _r.append((t, a))
                _seen_titles.add(t.lower())
    ROMANCE = _r
    logger.info(f"Romance: {len(ROMANCE)}")
except Exception:
    ROMANCE = []

try:
    from app.taxonomy.fantasy_seed_data import FANTASY_SEED_BOOKS

    _f = []
    for g, b in FANTASY_SEED_BOOKS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _f.append((t, a))
                _seen_titles.add(t.lower())
    FANTASY = _f
    logger.info(f"Fantasy: {len(FANTASY)}")
except Exception:
    FANTASY = []

try:
    from app.taxonomy.thriller_seed_data import THRILLER_MICROTROPE_CLUSTERS

    _t = []
    for g, b in THRILLER_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _t.append((t, a))
                _seen_titles.add(t.lower())
    THRILLER = _t
    logger.info(f"Thriller: {len(THRILLER)}")
except Exception:
    THRILLER = []

try:
    from app.taxonomy.horror_seed_data import HORROR_MICROTROPE_CLUSTERS

    _h = []
    for g, b in HORROR_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _h.append((t, a))
                _seen_titles.add(t.lower())
    HORROR = _h
    logger.info(f"Horror: {len(HORROR)}")
except Exception:
    HORROR = []

try:
    from app.taxonomy.scifi_seed_data import SCIFI_MICROTROPE_CLUSTERS

    _s = []
    for g, b in SCIFI_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _s.append((t, a))
                _seen_titles.add(t.lower())
    SCIFI = _s
    logger.info(f"SciFi: {len(SCIFI)}")
except Exception:
    SCIFI = []

try:
    from app.taxonomy.literary_seed_data import LITERARY_MICROTROPE_CLUSTERS

    _l = []
    for g, b in LITERARY_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _l.append((t, a))
                _seen_titles.add(t.lower())
    LITERARY = _l
    logger.info(f"Literary: {len(LITERARY)}")
except Exception:
    LITERARY = []

try:
    from app.taxonomy.nonfiction_seed_data import NONFICTION_MICROTROPE_CLUSTERS

    _n = []
    for g, b in NONFICTION_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _n.append((t, a))
                _seen_titles.add(t.lower())
    NONFICTION = _n
    logger.info(f"Nonfiction: {len(NONFICTION)}")
except Exception:
    NONFICTION = []

try:
    from app.taxonomy.historical_seed_data import HISTORICAL_MICROTROPE_CLUSTERS

    _hi = []
    for g, b in HISTORICAL_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _hi.append((t, a))
                _seen_titles.add(t.lower())
    HISTORICAL = _hi
    logger.info(f"Historical Fiction: {len(HISTORICAL)}")
except Exception:
    HISTORICAL = []

try:
    from app.taxonomy.mystery_seed_data import MYSTERY_MICROTROPE_CLUSTERS

    _m = []
    for g, b in MYSTERY_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _m.append((t, a))
                _seen_titles.add(t.lower())
    MYSTERY = _m
    logger.info(f"Mystery: {len(MYSTERY)}")
except Exception:
    MYSTERY = []

try:
    from app.taxonomy.memoir_seed_data import MEMOIR_MICROTROPE_CLUSTERS

    _me = []
    for g, b in MEMOIR_MICROTROPE_CLUSTERS.items():
        for t, a in b:
            if t.lower() not in _seen_titles:
                _me.append((t, a))
                _seen_titles.add(t.lower())
    MEMOIR = _me
    logger.info(f"Memoir: {len(MEMOIR)}")
except Exception:
    MEMOIR = []


def seed():
    from app.services.enrichment_service import enrich_book

    all_books = (
        FLASHCARD_POOL
        + ROMANCE
        + FANTASY
        + THRILLER
        + HORROR
        + SCIFI
        + LITERARY
        + NONFICTION
        + HISTORICAL
        + MYSTERY
        + MEMOIR
    )
    logger.info(
        f"Total: {len(all_books)} (core:{len(FLASHCARD_POOL)} rom:{len(ROMANCE)} fan:{len(FANTASY)} thr:{len(THRILLER)} hor:{len(HORROR)} sci:{len(SCIFI)} lit:{len(LITERARY)} nf:{len(NONFICTION)} hist:{len(HISTORICAL)} mys:{len(MYSTERY)} mem:{len(MEMOIR)})"
    )

    # Fresh connection — psycopg2 needs explicit sslmode for Supabase pooler
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from app.config import settings

    _uri = settings.DATABASE_URI
    if "?" not in _uri:
        _uri += "?sslmode=require&connect_timeout=10"
    else:
        _uri += "&sslmode=require&connect_timeout=10"
    _seed_engine = create_engine(_uri, poolclass=NullPool)
    _SeedSession = sessionmaker(bind=_seed_engine)
    db = _SeedSession()
    enriched = skipped = failed = 0
    consecutive_failures = 0
    MAX_CONSECUTIVE = 8
    tavily_fails = 0

    try:
        for i, (title, author) in enumerate(all_books, 1):
            try:
                existing = (
                    db.execute(
                        select(Work).where(sf.lower(Work.title) == title.lower())
                    )
                    .scalars()
                    .first()
                )
                if existing and existing.enrichment_status == "complete":
                    cache = db.execute(
                        select(EnrichmentCache).where(
                            EnrichmentCache.work_uuid == existing.work_uuid
                        )
                    ).scalar_one_or_none()
                    if cache and not cache.flashcard_pool:
                        cache.flashcard_pool = True
                        db.commit()
                    skipped += 1
                    consecutive_failures = 0
                    print(f"[{i}/{len(all_books)}] SKIP {title}", flush=True)
                    continue

                print(f"[{i}/{len(all_books)}] Enriching {title}...", flush=True)
                work = enrich_book(
                    db, title=title, author_name=author, skip_tavily=True
                )
                print(f"[{i}/{len(all_books)}] OK {title}", flush=True)
                cache = db.execute(
                    select(EnrichmentCache).where(
                        EnrichmentCache.work_uuid == work.work_uuid
                    )
                ).scalar_one()
                cache.flashcard_pool = True
                db.commit()
                enriched += 1
                consecutive_failures = 0
                time.sleep(0.3)

            except Exception as e:
                err = str(e).lower()
                db.rollback()
                is_gb = any(
                    kw in err
                    for kw in [
                        "503",
                        "service unavailable",
                        "timed out",
                        "timeout",
                        "ssl",
                        "connection",
                        "dns",
                        "name or service not known",
                        "handshake",
                        "connect",
                    ]
                )
                if is_gb:
                    consecutive_failures += 1
                    failed += 1
                    print(
                        f"[{i}/{len(all_books)}] FAIL {title} (GB {consecutive_failures}/{MAX_CONSECUTIVE})"
                    )
                    if consecutive_failures >= MAX_CONSECUTIVE:
                        logger.error(
                            f"STOPPING: {consecutive_failures} consecutive GB failures"
                        )
                        break
                elif (
                    "tavily" in err
                    or "usage limit" in err
                    or "quota" in err
                    or "exceeds" in err
                ):
                    tavily_fails += 1
                    failed += 1
                    print(f"[{i}/{len(all_books)}] FAIL {title} (Tavily quota)")
                    if tavily_fails >= 3:
                        logger.error("STOPPING: Tavily quota exhausted")
                        break
                else:
                    consecutive_failures = 0
                    failed += 1
                    print(f"[{i}/{len(all_books)}] FAIL {title}: {e}")
        logger.info(f"Done. enriched={enriched} skipped={skipped} failed={failed}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
