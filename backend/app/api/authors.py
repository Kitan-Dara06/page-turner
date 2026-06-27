import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.authors import Person
from app.models.events import EventType, InteractionEvent
from app.models.series import Series

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{person_uuid}/catalog")
def get_author_catalog(
    person_uuid: str,
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    FR-AT-03: Author Catalog View.
    Returns pen names, series in float order, and per-work is_read + series is_complete
    flags for the authenticated user.
    """
    person = db.execute(
        select(Person).where(Person.person_uuid == person_uuid)
    ).scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Author not found.")

    # One query for all read work UUIDs
    _read_rows = (
        db.execute(
            select(InteractionEvent.work_uuid).where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type == EventType.LOGGED_READ,
            )
        )
        .scalars()
        .all()
    )
    _read_set = {str(wu) for wu in _read_rows}

    series_records = (
        db.execute(select(Series).where(Series.person_uuid == person_uuid))
        .scalars()
        .all()
    )

    catalog_response = {
        "canonical_name": person.canonical_name,
        "person_uuid": person_uuid,
        "pen_names": [
            {"display_name": pn.display_name, "pen_name_uuid": str(pn.pen_name_uuid)}
            for pn in person.pen_names
        ],
        "series": [],
        "standalones": [],
    }

    for s in series_records:
        series_works = []
        core_read = 0
        core_total = 0

        for link in sorted(s.works, key=lambda x: x.order_float):
            wu = str(link.work.work_uuid)
            is_read = wu in _read_set
            series_works.append(
                {
                    "work_uuid": wu,
                    "title": link.work.title,
                    "order": link.order_float,
                    "is_core": link.is_core_storyline,
                    "is_read": is_read,
                }
            )
            if link.is_core_storyline:
                core_total += 1
                if is_read:
                    core_read += 1

        catalog_response["series"].append(
            {
                "series_uuid": str(s.series_uuid),
                "title": s.title,
                "works": series_works,
                "is_complete": core_total > 0 and core_read >= core_total,
            }
        )

    return catalog_response
