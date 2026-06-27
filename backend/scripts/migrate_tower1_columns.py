"""
Add missing Tower 1 columns to user_profiles table (SRS §4.2).

Run once: PYTHONPATH=. .venv/bin/python scripts/migrate_tower1_columns.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

from app.db.session import engine

COLUMNS = [
    # Universal (12 new)
    ("violence_tolerance", "FLOAT"),
    ("prose_density", "FLOAT"),
    ("narrative_linearity", "FLOAT"),
    ("plot_vs_character", "FLOAT"),
    ("setting_scope", "FLOAT"),
    ("speculative_deviation", "FLOAT"),
    ("world_building_appetite", "FLOAT"),
    ("emotional_intensity", "FLOAT"),
    ("series_completion_tendency", "FLOAT"),
    ("reread_tendency", "FLOAT"),
    ("pov_structure", "FLOAT"),
    ("protagonist_agency", "FLOAT"),
    # Non-Fiction (2 new)
    ("factual_density", "FLOAT"),
    ("instructional_vs_conceptual", "FLOAT"),
    # Romance (4 new)
    ("hea_requirement", "FLOAT"),
    ("relationship_ratio", "FLOAT"),
    ("role_rigidity", "FLOAT"),
    ("relationship_pace", "FLOAT"),
]


def migrate():
    with engine.connect() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'user_profiles'"
                )
            ).all()
        }
        added = 0
        for col_name, col_type in COLUMNS:
            if col_name in existing:
                print(f"  SKIP {col_name} (already exists)")
                continue
            conn.execute(
                text(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_type}")
            )
            conn.commit()
            print(f"  ADD  {col_name}")
            added += 1
        print(f"\nDone. Added {added} columns, skipped {len(COLUMNS) - added}.")


if __name__ == "__main__":
    migrate()
