import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.integrations import google_books as gb
from app.models.authors import Person
from app.models.books import Work
from app.models.events import EventType, InteractionEvent
from app.models.tracked_authors import TrackedAuthor
from app.models.users import User
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Check for releases within this window — past AND future
RELEASE_WINDOW_PAST_DAYS = 90
RELEASE_WINDOW_FUTURE_DAYS = 90


def _auto_track_for_user(db: Session, user_uuid, person_uuid):
    """Ensure the user is tracking this author. Idempotent."""
    existing = db.execute(
        select(TrackedAuthor).where(
            TrackedAuthor.user_uuid == user_uuid,
            TrackedAuthor.person_uuid == person_uuid,
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(
            TrackedAuthor(
                user_uuid=user_uuid,
                person_uuid=person_uuid,
            )
        )
        return True
    return False


@celery_app.task(bind=True, max_retries=3, acks_late=True)
def sync_tracked_authors_from_reads(self):
    """
    Backfills TrackedAuthor entries from existing LOGGED_READ events.
    One-off / periodic sync — after this, auto-tracking in the feedback
    endpoint keeps things current. Idempotent.
    """
    db: Session = SessionLocal()
    try:
        # Use raw SQL to avoid ORM mapper issues with Person→Series relationship
        rows = db.execute(
            text(
                "SELECT DISTINCT ie.user_uuid, w.person_uuid "
                "FROM interaction_events ie "
                "JOIN works w ON w.work_uuid = ie.work_uuid "
                "WHERE ie.event_type = 'logged_read' "
                "AND ie.work_uuid IS NOT NULL"
            )
        ).all()

        tracked = 0
        for user_uuid, person_uuid in rows:
            if _auto_track_for_user(db, user_uuid, person_uuid):
                tracked += 1

        if tracked:
            db.commit()
            logger.info(
                f"Auto-tracked {tracked} new author-user pairs from read history."
            )
        else:
            logger.info("No new authors to track from read history.")
    except Exception:
        db.rollback()
        logger.exception("Sync tracked authors failed")
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, acks_late=True)
def check_tracked_authors_for_releases(self, limit: int = 50):
    """
    FR-AT-02: Release Alert Generation.
    Iterates over ALL users' TrackedAuthor records. For each tracked author,
    checks Google Books for recent releases and writes InteractionEvent alerts.
    """
    db: Session = SessionLocal()
    try:
        logger.info(f"Checking tracked authors for new releases (limit={limit})...")

        # Get all tracked author entries, ordered by last checked (oldest first)
        tracked_rows = (
            db.execute(
                select(TrackedAuthor)
                .order_by(TrackedAuthor.last_known_release_date.asc().nullsfirst())
                .limit(limit)
            )
            .scalars()
            .all()
        )

        if not tracked_rows:
            logger.info("No tracked authors found — skipping release check.")
            return

        new_releases = 0
        past_cutoff = datetime.now(timezone.utc) - timedelta(
            days=RELEASE_WINDOW_PAST_DAYS
        )
        future_cutoff = datetime.now(timezone.utc) + timedelta(
            days=RELEASE_WINDOW_FUTURE_DAYS
        )

        for ta in tracked_rows:
            person = db.execute(
                select(Person).where(Person.person_uuid == ta.person_uuid)
            ).scalar_one_or_none()
            if not person:
                continue

            author_name = person.canonical_name
            logger.info(f"Checking releases for: {author_name} (user {ta.user_uuid})")

            try:
                results = gb.search_by_title_author(
                    title="",
                    author=author_name,
                )
            except Exception:
                logger.warning(f"Google Books API failed for {author_name}, skipping.")
                continue

            found_for_author = 0
            for item in results:
                vol = item.get("volumeInfo", {})
                title = vol.get("title", "")
                pub_date = vol.get("publishedDate", "")
                isbns = [
                    i.get("identifier")
                    for i in vol.get("industryIdentifiers", [])
                    if i.get("type") in ("ISBN_13", "ISBN_10")
                ]

                # Parse publication date
                try:
                    if len(pub_date) == 4:
                        pub = datetime(int(pub_date), 1, 1)
                    elif len(pub_date) == 7:
                        pub = datetime.strptime(pub_date, "%Y-%m")
                    else:
                        pub = datetime.strptime(pub_date, "%Y-%m-%d")
                    pub = pub.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    continue

                if pub < past_cutoff or pub > future_cutoff:
                    continue

                # Only skip if an UNDISMISSED notification already exists for this release.
                # If the user dismissed the old one, create a fresh event so it re-surfaces.
                already_notified = db.execute(
                    select(InteractionEvent.event_uuid).where(
                        InteractionEvent.user_uuid == ta.user_uuid,
                        InteractionEvent.event_type == EventType.AUTHOR_NEW_RELEASE,
                        InteractionEvent.mood_tags["title"].as_string() == title,
                        InteractionEvent.mood_tags["author_name"].as_string()
                        == author_name,
                        InteractionEvent.mood_tags["dismissed"].as_boolean() == False,
                    )
                ).scalar_one_or_none()

                if already_notified:
                    continue

                # Find or create the Work
                work = db.execute(
                    select(Work).where(
                        func.lower(Work.title) == title.lower(),
                        Work.person_uuid == ta.person_uuid,
                    )
                ).scalar_one_or_none()

                event = InteractionEvent(
                    user_uuid=ta.user_uuid,
                    work_uuid=work.work_uuid if work else None,
                    event_type=EventType.AUTHOR_NEW_RELEASE,
                    mood_tags={
                        "title": title,
                        "author_name": author_name,
                        "publication_date": pub_date,
                        "isbn": isbns[0] if isbns else None,
                        "dismissed": False,
                    },
                )
                db.add(event)
                new_releases += 1
                found_for_author += 1

            # Update last known release date
            if found_for_author > 0:
                ta.last_known_release_date = datetime.now(timezone.utc)

            logger.info(f"  {author_name}: {found_for_author} new releases found")

        if new_releases:
            db.commit()
            logger.info(
                f"Found {new_releases} new releases across {len(tracked_rows)} tracked-author entries."
            )
        else:
            db.rollback()
            logger.info("No new releases found.")

    except Exception:
        db.rollback()
        logger.exception("Release check failed")
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=2, acks_late=True)
def seed_niche_genre_from_books(self, work_uuids: list[str]):
    """
    FR-SEED-01: When a user seeds with books from a niche genre, detect if the
    genre is under-represented in our DB and populate 10+ similar books via Google
    Books + enrichment pipeline.
    """
    db: Session = SessionLocal()
    try:
        from sqlalchemy import func as sa_func

        from app.models.authors import Person
        from app.models.books import Edition
        from app.models.tropes import BookTrope, Trope

        trope_counter: dict[str, int] = {}
        for wuid in work_uuids:
            tropes = (
                db.execute(
                    select(Trope.canonical_name)
                    .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
                    .where(BookTrope.work_uuid == wuid)
                    .where(Trope.is_root_hub == False)
                )
                .scalars()
                .all()
            )
            for t in tropes:
                trope_counter[t] = trope_counter.get(t, 0) + 1

        if not trope_counter:
            logger.info("Seed books have no tropes yet — enrichment may be pending.")
            return

        dominant = max(trope_counter, key=trope_counter.get)
        existing_count = (
            db.execute(
                select(sa_func.count(BookTrope.work_uuid))
                .join(Trope, Trope.trope_uuid == BookTrope.trope_uuid)
                .where(Trope.canonical_name == dominant)
            ).scalar()
            or 0
        )

        if existing_count >= 10:
            logger.info(f"'{dominant}' has {existing_count} books — sufficient.")
            return

        needed = 10 - existing_count
        logger.info(
            f"'{dominant}' only has {existing_count} books. Searching for {needed} more..."
        )

        import httpx

        from app.config import settings

        params = {
            "q": dominant.replace("_", " "),
            "key": settings.GOOGLE_BOOKS_API_KEY,
            "maxResults": 15,
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                resp = client.get(
                    "https://www.googleapis.com/books/v1/volumes", params=params
                )
                resp.raise_for_status()
                results = resp.json().get("items", [])
        except Exception:
            logger.warning(f"Google Books search failed for: {dominant}")
            return

        created = 0
        for item in results:
            if created >= needed:
                break
            vol = item.get("volumeInfo", {})
            title = vol.get("title", "")
            if not title:
                continue
            authors = vol.get("authors", [])
            author_name = authors[0] if authors else "Unknown"

            existing = (
                db.execute(
                    select(Work).where(sa_func.lower(Work.title) == title.lower())
                )
                .scalars()
                .all()
            )
            if any(
                w.author and w.author.canonical_name.lower() == author_name.lower()
                for w in existing
            ):
                continue

            person = db.execute(
                select(Person).where(
                    sa_func.lower(Person.canonical_name) == author_name.lower()
                )
            ).scalar_one_or_none()
            if not person:
                person = Person(canonical_name=author_name)
                db.add(person)
                db.flush()

            work = Work(
                title=title, person_uuid=person.person_uuid, enrichment_status="pending"
            )
            db.add(work)
            db.flush()

            isbns = [
                i.get("identifier")
                for i in vol.get("industryIdentifiers", [])
                if i.get("type") in ("ISBN_13", "ISBN_10")
            ]
            if isbns:
                db.add(
                    Edition(work_uuid=work.work_uuid, isbn=isbns[0], format="unknown")
                )

            created += 1
            logger.info(f"  Seeded: {title} by {author_name}")

        if created > 0:
            db.commit()
            logger.info(
                f"Seeded {created} books for '{dominant}' (had {existing_count})"
            )
            from app.workers.enrichment_tasks import enrich_single_work

            for w in (
                db.execute(
                    select(Work)
                    .where(Work.enrichment_status == "pending")
                    .limit(created)
                )
                .scalars()
                .all()
            ):
                enrich_single_work.delay(str(w.work_uuid))
        else:
            db.rollback()

    except Exception:
        db.rollback()
        logger.exception("Niche population failed")
    finally:
        db.close()
