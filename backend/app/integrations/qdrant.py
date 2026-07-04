"""
Qdrant Vector Database — Collection management and search.
Implements SRS Section 5.2 with payload index creation and retry wrappers.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize client (can point to local Docker or Qdrant Cloud via settings)
client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

# Fields that must have a payload index for filtered queries.
# The Tower 2 latent profile and orphan-queue review both filter by work_uuid.
# trope_names is a keyword array — used for MatchAny trope filtering in similarity queries.
REQUIRED_PAYLOAD_INDEXES = [
    {"name": "work_uuid", "type": "keyword"},
    {"name": "hallucination_verified", "type": "keyword"},
    {"name": "trope_names", "type": "keyword"},
]


def _ensure_payload_indexes(collection_name: str) -> None:
    """Create required payload indexes if they don't already exist.

    Without these, filtered queries (e.g. ``filter_dict={"work_uuid": ...}``)
    return HTTP 400: "Index required but not found for 'work_uuid'".
    """
    try:
        existing = client.get_collection(collection_name).config.params
        for idx_conf in REQUIRED_PAYLOAD_INDEXES:
            name = idx_conf["name"]
            # Qdrant v1.18 doesn't have a clean "list indexes" method,
            # so we try to create and silently ignore duplicates.
            client.create_payload_index(
                collection_name=collection_name,
                field_name=name,
                field_type=idx_conf["type"],
            )
            logger.debug(f"Payload index '{name}' ensured on '{collection_name}'.")
    except Exception as e:
        # "already exists" is harmless — the index is there.
        if "already exists" in str(e).lower():
            return
        logger.warning(f"Failed to ensure payload index on '{collection_name}': {e}")


def create_collection_if_not_exists(
    collection_name: str,
    vector_size: int = None,
):
    """Creates the collection using Cosine distance if it doesn't exist.

    Also ensures required payload indexes exist so filtered queries
    (Tower 2 latent updates, orphan review) don't 400.

    vector_size defaults to settings.QDRANT_VECTOR_SIZE (1536 for voyage-large-2).
    """
    size = vector_size or settings.QDRANT_VECTOR_SIZE
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
        logger.info(f"Created collection '{collection_name}' (size={size}).")

    _ensure_payload_indexes(collection_name)


def recreate_collection(collection_name: str, vector_size: int = None):
    """
    Drops and recreates a collection with the correct vector dimension.
    Use when switching embedding models (e.g. 768-dim placeholder → 1536-dim Voyage).
    All existing vectors are wiped — re-run the seed after calling this.
    """
    size = vector_size or settings.QDRANT_VECTOR_SIZE
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=size, distance=Distance.COSINE),
    )
    _ensure_payload_indexes(collection_name)


def upsert_vector(
    collection_name: str, point_id: str, vector: list[float], payload: dict
):
    """Inserts or updates a single book vector with its metadata."""
    client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=point_id,  # Must be a UUID string
                vector=vector,
                payload=payload,
            )
        ],
    )


def search_knn(
    collection_name: str,
    query_vector: list[float],
    limit: int = 10,
    filter_dict: dict = None,
    trope_filter: Optional[List[str]] = None,
    timeout_seconds: int = 5,
    retries: int = 2,
) -> List[Dict[str, Any]]:
    """Performs semantic search with retry + timeout.

    Qdrant Cloud connections can stall on SSL handshake under flaky networks.
    We retry up to ``retries`` times with a short per-attempt timeout.

    Args:
        filter_dict:   Payload filter, e.g. ``{"work_uuid": "..."}``.
                       Requires a ``keyword`` payload index on the field.
        trope_filter:  List of canonical trope names. When provided, Qdrant
                       returns only points whose ``trope_names`` payload contains
                       at least one of these values (MatchAny / logical OR).
                       This moves trope filtering from Python post-processing
                       to the DB layer, dramatically shrinking the candidate pool
                       before Python sees it.
                       Requires a ``keyword`` payload index on ``trope_names``.
        timeout_seconds: Per-attempt timeout for the gRPC/REST call.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    kwargs: Dict[str, Any] = {
        "collection_name": collection_name,
        "query": query_vector,
        "limit": limit,
        "with_payload": True,
        "with_vectors": False,
    }

    conditions = []
    if filter_dict:
        conditions.extend(
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filter_dict.items()
        )
    if trope_filter:
        # MatchAny: point passes if trope_names payload contains ANY of these tropes.
        # This is a Qdrant-native OR filter — far cheaper than post-filtering in Python.
        conditions.append(
            FieldCondition(
                key="trope_names",
                match=MatchAny(any=trope_filter),
            )
        )
    if conditions:
        kwargs["query_filter"] = Filter(must=conditions)

    last_error = None
    for attempt in range(1 + retries):
        try:
            results = client.query_points(
                **kwargs,  # type: ignore[arg-type]
                # qdrant_client accepts timeout as a query-level param
                timeout=timeout_seconds,
            )
            return [
                {"id": hit.id, "score": hit.score, "payload": hit.payload}
                for hit in results.points
            ]
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # Don't retry on 400 (bad request — payload index missing, won't recover)
            if "400" in err_str or "bad request" in err_str:
                logger.error(
                    f"Qdrant search_knn 400 on '{collection_name}': {e}. "
                    "Check that payload indexes exist."
                )
                raise
            logger.warning(
                f"Qdrant search_knn attempt {attempt + 1}/{1 + retries} failed: {e}"
            )
            if attempt < retries:
                time.sleep(1.5**attempt)  # exponential backoff: 1s, 1.5s

    logger.error(
        f"Qdrant search_knn exhausted {retries} retries. Last error: {last_error}"
    )
    return []


def fetch_vector_by_id(
    collection_name: str,
    point_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a single point by its UUID (primary key).

    This avoids the filtered-search approach that requires a payload index.
    Used by the Tower 2 latent profile update to read the book's embedding.

    Returns the point dict with ``id``, ``payload``, and optionally ``vector``,
    or ``None`` if the point doesn't exist.
    """
    try:
        points = client.retrieve(
            collection_name=collection_name,
            ids=[point_id],
            with_payload=True,
            with_vectors=True,
        )
        if not points:
            return None
        pt = points[0]
        return {
            "id": pt.id,
            "payload": pt.payload,
            "vector": pt.vector,
        }
    except Exception as e:
        logger.error(f"Qdrant fetch by id {point_id} failed: {e}")
        return None
