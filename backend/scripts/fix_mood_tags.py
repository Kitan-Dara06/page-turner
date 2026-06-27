"""Fix romance activation — variable name mismatch and missing except."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

from app.db.session import SessionLocal

db = SessionLocal()
db.execute(
    text("""
    UPDATE interaction_events
    SET mood_tags = mood_tags::jsonb
    WHERE mood_tags IS NOT NULL
""")
)
db.commit()
print("Fixed mood_tags type")
db.close()
