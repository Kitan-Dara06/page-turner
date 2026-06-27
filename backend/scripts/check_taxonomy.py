"""Check taxonomy mappings for seeded flashcard pool."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.config import settings

engine = create_engine(settings.DATABASE_URI, pool_pre_ping=True, pool_size=1)
with engine.connect() as c:
    pool = c.execute(
        text("SELECT COUNT(*) FROM enrichment_cache WHERE flashcard_pool = true")
    ).scalar()
    total = c.execute(text("SELECT COUNT(*) FROM enrichment_cache")).scalar()
    print(f"Flashcard pool: {pool}/{total} enriched books")

    rows = c.execute(
        text("""
            SELECT w.title, COUNT(bt.trope_uuid) as trope_count
            FROM works w
            LEFT JOIN book_tropes bt ON w.work_uuid = bt.work_uuid
            WHERE w.enrichment_status = 'complete'
            GROUP BY w.title
            ORDER BY trope_count DESC
            LIMIT 15
        """)
    ).all()

    print(f"\nBooks by trope mappings:")
    for title, count in rows:
        print(f"  {count} tropes — {title[:50]}")

    orphans = c.execute(text("SELECT COUNT(*) FROM orphan_queue")).scalar()
    print(f"\nOrphan queue items: {orphans}")

    if orphans and orphans > 0:
        print(f"\nSample orphans:")
        o = c.execute(
            text(
                "SELECT tag_text, frequency_count FROM orphan_queue ORDER BY frequency_count DESC LIMIT 8"
            )
        ).all()
        for tag, freq in o:
            print(f'  "{tag}" (seen {freq}x)')

    print(
        f"\nTotal taxonomy nodes: {c.execute(text('SELECT COUNT(*) FROM tropes')).scalar()}"
    )
    print(
        f"Total DAG edges: {c.execute(text('SELECT COUNT(*) FROM trope_parents')).scalar()}"
    )
