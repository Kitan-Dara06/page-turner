import logging

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services import tbr_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, acks_late=True)
def apply_tbr_decay_formula(self):
    """
    FR-TBR-02: TBR Priority Decay.
    Scheduled beat task — applies exponential decay to all active TBR entries.
    """
    db: Session = SessionLocal()
    try:
        logger.info("Applying global TBR priority decay...")
        tbr_service.apply_global_tbr_decay(db)
    finally:
        db.close()
