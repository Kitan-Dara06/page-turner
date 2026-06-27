import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal

# Preload all models to resolve SQLAlchemy relationships
from app.models import (
    authors,
    books,
    enrichment,
    events,
    recommendations,
    series,
    tbr,
    tropes,
    users,
)
from app.models.tropes import OrphanQueue

db = SessionLocal()
rows = (
    db.execute(
        select(OrphanQueue).order_by(OrphanQueue.frequency_count.desc()).limit(50)
    )
    .scalars()
    .all()
)

header = f"{'TAG':<35} {'FREQ':>5}  {'LAST SEEN':>10}"
print(header)
print("-" * len(header))
for r in rows:
    tag = r.tag_text[:34]
    freq = r.frequency_count
    seen = str(r.last_seen)[:10]
    print(f"{tag:<35} {freq:>5}  {seen:>10}")
print(f"\nTotal: {len(rows)} orphans")
db.close()
