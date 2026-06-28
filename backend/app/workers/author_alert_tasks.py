import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
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

# Only check releases published within this many days
RELEASE_WINDOW_DAYS = 30


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
        # Find all user-author pairs from LOGGED_READ events
        rows = db.execute(
            select(
                InteractionEvent.user_uuid,
                Work.person_uuid,
            )
            .join(Work, Work.work_uuid == InteractionEvent.work_uuid)
            .where(
                InteractionEvent.event_type == EventType.LOGGED_READ,
                InteractionEvent.work_uuid.isnot(None),
            )
            .distinct()
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
        cutoff = datetime.now(timezone.utc) - timedelta(days=RELEASE_WINDOW_DAYS)

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

                if pub < cutoff:
                    continue

                # Check if already notified for this user+title+author
                already_notified = db.execute(
                    select(InteractionEvent.event_uuid).where(
                        InteractionEvent.user_uuid == ta.user_uuid,
                        InteractionEvent.event_type == EventType.AUTHOR_NEW_RELEASE,
                        InteractionEvent.mood_tags["title"].as_string() == title,
                        InteractionEvent.mood_tags["author_name"].as_string()
                        == author_name,
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
