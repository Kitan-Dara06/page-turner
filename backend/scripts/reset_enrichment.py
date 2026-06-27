"""Reset flashcard pool books for re-enrichment."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

from app.db.session import SessionLocal

db = SessionLocal()
db.execute(
    text(
        "UPDATE works SET enrichment_status = 'pending' "
        "WHERE work_uuid IN (SELECT work_uuid FROM enrichment_cache WHERE flashcard_pool = true)"
    )
)
db.execute(
    text(
        "UPDATE enrichment_cache SET last_completed_step = NULL WHERE flashcard_pool = true"
    )
)
db.commit()
count = db.execute(
    text("SELECT COUNT(*) FROM enrichment_cache WHERE flashcard_pool = true")
).scalar()
print(f"Reset {count} flashcard pool books for re-enrichment")
db.close()
