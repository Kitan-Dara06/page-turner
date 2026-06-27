"""Set reject hallucinated books with no Google Books / OpenLibrary metadata."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

from app.db.session import SessionLocal

db = SessionLocal()
# Delete books enriched from LLM suggestions that have zero metadata
db.execute(
    text("""
    DELETE FROM enrichment_cache
    WHERE flashcard_pool = false
    AND description IS NULL
    AND raw_categories IS NULL
    AND subject_tags IS NULL
""")
)
db.execute(
    text("""
    DELETE FROM works
    WHERE enrichment_status = 'complete'
    AND work_uuid NOT IN (SELECT work_uuid FROM enrichment_cache)
""")
)
db.commit()
print("Cleaned up hallucinated books with no metadata")
db.close()
