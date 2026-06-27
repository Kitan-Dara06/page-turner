import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.integrations import google_books as gb
from app.models.authors import Person
from app.models.books import Work
from app.models.events import EventType, InteractionEvent
from app.models.users import User  # register users table for FK resolution
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Only check releases published within this many days
RELEASE_WINDOW_DAYS = 30


@celery_app.task(bind=True, max_retries=3, acks_late=True)
def check_tracked_authors_for_releases(self, limit: int = 50):
    """
    FR-AT-02: Release Alert Generation.
    For each user, find authors they've read. Check Google Books for recent
    releases by those authors. Write InteractionEvent for each new release found.
    """
    db: Session = SessionLocal()
    try:
        logger.info(f"Checking tracked authors for new releases (limit={limit})...")

        # Phase 1: mock user only. Phase 2: iterate all users.
        mock_uuid = UUID("00000000-0000-0000-0000-000000000001")

        # Find authors the user has read
        read_author_rows = (
            db.execute(
                select(func.distinct(Work.person_uuid))
                .join(InteractionEvent, InteractionEvent.work_uuid == Work.work_uuid)
                .where(
                    InteractionEvent.user_uuid == mock_uuid,
                    InteractionEvent.event_type == EventType.LOGGED_READ,
                )
                .limit(limit)
            )
            .scalars()
            .all()
        )

        if not read_author_rows:
            logger.info("No read authors found — skipping release check.")
            return

        new_releases = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=RELEASE_WINDOW_DAYS)

        for person_uuid in read_author_rows:
            person = db.execute(
                select(Person).where(Person.person_uuid == person_uuid)
            ).scalar_one_or_none()
            if not person:
                continue

            author_name = person.canonical_name
            logger.info(f"Checking releases for: {author_name}")

            try:
                results = gb.search_by_title_author(
                    title="",  # empty — search by author only
                    author=author_name,
                )
            except Exception:
                continue

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

                # Check if we already notified about this release
                already_notified = db.execute(
                    select(InteractionEvent.event_uuid).where(
                        InteractionEvent.user_uuid == mock_uuid,
                        InteractionEvent.event_type == EventType.AUTHOR_NEW_RELEASE,
                        InteractionEvent.work_uuid.is_(None),
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
                        Work.person_uuid == person_uuid,
                    )
                ).scalar_one_or_none()

                event = InteractionEvent(
                    user_uuid=mock_uuid,
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
                logger.info(f"  New release: {title} by {author_name} ({pub_date})")

        if new_releases:
            db.commit()
            logger.info(
                f"Found {new_releases} new releases across {len(read_author_rows)} authors."
            )
        else:
            db.rollback()
            logger.info("No new releases found.")

    except Exception:
        db.rollback()
        logger.exception("Release check failed")
    finally:
        db.close()
