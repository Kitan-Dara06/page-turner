import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.models.tropes import OrphanQueue, Trope, TropeAlias

logger = logging.getLogger(__name__)
router = APIRouter()


class MapRequest(BaseModel):
    trope_uuid: str

    @field_validator("trope_uuid")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid UUID format: {v!r}")
        return v


# ── List orphans ──────────────────────────────────────────────────────


@router.get("/orphans", dependencies=[Depends(require_admin)])
def list_orphans(min_frequency: int = 3, db: Session = Depends(get_db)):
    """Returns orphan tags above a frequency threshold, sorted descending."""
    rows = (
        db.execute(
            select(OrphanQueue)
            .where(OrphanQueue.frequency_count >= min_frequency)
            .order_by(OrphanQueue.frequency_count.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )

    return {
        "count": len(rows),
        "orphans": [
            {
                "tag_text": r.tag_text,
                "source": r.source,
                "frequency_count": r.frequency_count,
                "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            }
            for r in rows
        ],
    }


# ── Promote orphan → canonical Trope ──────────────────────────────────


@router.post("/orphans/{tag_text}/promote", dependencies=[Depends(require_admin)])
def promote_orphan(tag_text: str, db: Session = Depends(get_db)):
    """Creates a new canonical Trope from an orphan tag."""
    orphan = db.execute(
        select(OrphanQueue).where(OrphanQueue.tag_text == tag_text)
    ).scalar_one_or_none()

    if not orphan:
        raise HTTPException(status_code=404, detail="Orphan tag not found.")

    # Title-case the tag for canonical name
    canonical_name = tag_text.replace("_", " ").title().strip()

    # Check if a Trope with this name already exists
    existing = db.execute(
        select(Trope).where(func.lower(Trope.canonical_name) == canonical_name.lower())
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Trope '{canonical_name}' already exists.",
        )

    # Create the new Trope
    new_trope = Trope(
        canonical_name=canonical_name,
        depth_level=0,
        is_root_hub=False,
    )
    db.add(new_trope)
    db.flush()

    # Create an alias from the orphan tag to the new Trope
    alias = TropeAlias(
        trope_uuid=new_trope.trope_uuid,
        alias_text=tag_text,
        source="orphan_promoted",
    )
    db.add(alias)

    # Remove from orphan queue
    db.delete(orphan)

    db.commit()

    logger.info(f"Promoted orphan '{tag_text}' → Trope '{canonical_name}'")
    return {
        "status": "promoted",
        "trope_uuid": str(new_trope.trope_uuid),
        "canonical_name": canonical_name,
    }


# ── Map orphan → existing Trope ───────────────────────────────────────


@router.post("/orphans/{tag_text}/map", dependencies=[Depends(require_admin)])
def map_orphan(tag_text: str, request: MapRequest, db: Session = Depends(get_db)):
    """Maps an orphan tag to an existing canonical Trope via TropeAlias."""
    orphan = db.execute(
        select(OrphanQueue).where(OrphanQueue.tag_text == tag_text)
    ).scalar_one_or_none()

    if not orphan:
        raise HTTPException(status_code=404, detail="Orphan tag not found.")

    trope = db.execute(
        select(Trope).where(Trope.trope_uuid == request.trope_uuid)
    ).scalar_one_or_none()

    if not trope:
        raise HTTPException(status_code=404, detail="Target Trope not found.")

    # Create alias mapping
    alias = TropeAlias(
        trope_uuid=trope.trope_uuid,
        alias_text=tag_text,
        source="orphan_mapped",
    )
    db.add(alias)
    db.delete(orphan)
    db.commit()

    logger.info(f"Mapped orphan '{tag_text}' → Trope '{trope.canonical_name}'")
    return {
        "status": "mapped",
        "trope_uuid": str(trope.trope_uuid),
        "canonical_name": trope.canonical_name,
    }


# ── Dismiss orphan ────────────────────────────────────────────────────


@router.post("/orphans/{tag_text}/dismiss", dependencies=[Depends(require_admin)])
def dismiss_orphan(tag_text: str, db: Session = Depends(get_db)):
    """Removes an orphan tag from the queue."""
    orphan = db.execute(
        select(OrphanQueue).where(OrphanQueue.tag_text == tag_text)
    ).scalar_one_or_none()

    if not orphan:
        raise HTTPException(status_code=404, detail="Orphan tag not found.")

    db.delete(orphan)
    db.commit()

    return {"status": "dismissed", "tag_text": tag_text}


# ── List all canonical Tropes (for the Map dropdown) ──────────────────


@router.get("/tropes", dependencies=[Depends(require_admin)])
def list_tropes(db: Session = Depends(get_db)):
    """Returns all canonical tropes for the map-orphan dropdown."""
    rows = db.execute(
        select(Trope.canonical_name, Trope.trope_uuid).order_by(Trope.canonical_name)
    ).all()
    return {
        "tropes": [
            {"canonical_name": name, "trope_uuid": str(uuid)} for name, uuid in rows
        ]
    }
