"""
Recreate Qdrant Collection — migrate from 768-dim placeholder to 1536-dim Voyage.

Run ONCE before re-running seed_catalog.py:
    PYTHONPATH=$PWD .venv/bin/python scripts/recreate_qdrant_collection.py

WARNING: This deletes all existing vectors. Re-seed after running.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.integrations import qdrant

COLLECTION = "books_catalog"


def main():
    print(f"Target collection : {COLLECTION}")
    print(f"New vector size   : {settings.QDRANT_VECTOR_SIZE} dims (voyage-large-2)")
    print(f"Qdrant URL        : {settings.QDRANT_URL}")
    print()

    exists = qdrant.client.collection_exists(COLLECTION)
    if exists:
        info = qdrant.client.get_collection(COLLECTION)
        old_size = info.config.params.vectors.size
        print(f"Existing collection found — current vector size: {old_size}")
        if old_size == settings.QDRANT_VECTOR_SIZE:
            print("Collection already at the correct dimension. Nothing to do.")
            return
        confirm = input(
            f"\nThis will DROP '{COLLECTION}' and recreate it at {settings.QDRANT_VECTOR_SIZE} dims.\n"
            "All existing vectors will be lost. Type 'yes' to proceed: "
        )
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return
    else:
        print(f"Collection '{COLLECTION}' does not exist — creating fresh.")

    qdrant.recreate_collection(COLLECTION)
    print(f"\n✓ Collection '{COLLECTION}' recreated at {settings.QDRANT_VECTOR_SIZE} dims.")
    print("Run seed_catalog.py next to populate it with real embeddings.")


if __name__ == "__main__":
    main()
