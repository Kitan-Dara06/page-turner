"""List all book-trope mappings for manual review."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.config import settings

engine = create_engine(settings.DATABASE_URI, pool_pre_ping=True, pool_size=1)
with engine.connect() as c:
    rows = c.execute(
        text("""
            SELECT w.title, t.canonical_name, bt.confidence_score
            FROM book_tropes bt
            JOIN tropes t ON t.trope_uuid = bt.trope_uuid
            JOIN works w ON w.work_uuid = bt.work_uuid
            ORDER BY w.title, bt.confidence_score DESC
        """)
    ).all()

    current = ""
    for title, trope, score in rows:
        if title != current:
            print(f"\n=== {title} ===")
            current = title
        print(f"  {trope} ({score})")
