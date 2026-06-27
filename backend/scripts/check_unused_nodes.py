"""Check which taxonomy nodes have NO book mappings."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.config import settings

engine = create_engine(
    settings.DATABASE_URI,
    pool_pre_ping=True,
    pool_size=1,
    connect_args={"connect_timeout": 5},
)
with engine.connect() as c:
    rows = c.execute(
        text("""
            SELECT t.canonical_name, t.depth_level
            FROM tropes t
            LEFT JOIN book_tropes bt ON t.trope_uuid = bt.trope_uuid
            WHERE bt.work_uuid IS NULL
            ORDER BY t.depth_level, t.canonical_name
        """)
    ).all()

    print(f"Unused taxonomy nodes ({len(rows)}):")
    for name, depth in rows:
        print(f"  [depth {depth}] {name}")
