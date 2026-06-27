import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.books import Work
from app.models.tropes import BookTrope, Trope
from app.schemas.users import Tower1Profile

logger = logging.getLogger(__name__)

# --- FR-QR-05 Phase 1 Weight Definitions ---
# Total max positive: 1.00 | Total max penalty: -0.10
WEIGHT_VECTOR_SIMILARITY = 0.30  # down from 0.40 — shares weight with query-trope
WEIGHT_QUERY_TROPE = 0.15  # new — IDF-weighted overlap with query's implied tropes
WEIGHT_TOWER1_MATCH = 0.25  # down from 0.30 — long-term profile similarity
WEIGHT_TBR_BONUS = 0.10
WEIGHT_INTERESTED_BONUS = 0.05  # Soft positive — resurfacing nudge for interested books
WEIGHT_TEMPORAL = 0.05  # FR-QR-07: time-of-day / day-of-week reading pattern boost
WEIGHT_COMMUNITY_BUZZ = 0.10
PENALTY_RECENCY = -0.10


@dataclass
class CandidateContext:
    """
    Standardized payload for a book candidate entering the reranker.
    Abstracts away whether the book came from Qdrant, TBR, or LLM expansion.
    """

    work_uuid: str
    title: str
    base_vector_score: float  # 0.0–1.0 (Cosine similarity normalized)
    is_tbr_context_match: bool  # True if pulled from TBR with matching mood
    community_buzz_score: float  # 0.0–1.0 (From enrichment cache)
    seen_recently: bool  # True if surfaced recently but skipped
    book_inferred_profile: Dict[str, float]  # Book's Tower 1 equivalent values
    book_trope_names: List[str] = field(default_factory=list)  # Top canonical tropes
    is_interested: bool = False  # True if user has an INTERESTED event for this book
    is_narrative: bool = True  # False for non-fiction/non-narrative (zeroes Tower 1)
    is_in_tbr: bool = False  # True if this book is in the user's active TBR list
    description: Optional[str] = (
        None  # From EnrichmentCache, for expandable card detail
    )

    # Store original ORM object or dictionary for downstream delivery
    raw_record: Any = None

    # These are populated during the reranking process
    final_score: float = 0.0
    match_source: str = "vector"
    explanation_factors: List[str] = field(default_factory=list)


def rank_candidates(
    candidates: List[CandidateContext],
    user_profile: Tower1Profile,
    idf_weights: Optional[Dict[str, float]] = None,
    query_trope_names: Optional[List[str]] = None,
    anchor_defining_tropes: Optional[List[str]] = None,
    current_hour: Optional[int] = None,
    day_of_week: Optional[int] = None,
    temporal_preference: Optional[Dict[str, float]] = None,
    reader_phase: Optional[dict] = None,
) -> List[CandidateContext]:
    """
    Applies the Phase 1 contextual reranking formula to a list of retrieved candidates.
    Sorts descending by the final computed score.

    Args:
        idf_weights:            Pre-computed IDF weight map {canonical_name: float}.
                                From compute_trope_idf(). Required for query-trope scoring.
        query_trope_names:      Tropes implied by the current query (not the user's long-term
                                profile). Used for query-time relevance filtering. If None,
                                query-trope component is skipped (backwards compatible).
        anchor_defining_tropes: For similarity queries — the anchor book's highest-confidence
                                (1.0) tropes. These are the book's identity-level descriptors.
                                Candidates that share all defining tropes get a ×1.4 boost;
                                candidates that share none get a ×0.6 penalty.
        current_hour:           FR-QR-07 — hour of day (0-23) for temporal boost.
        day_of_week:            FR-QR-07 — day of week (0=Mon, 6=Sun) for temporal boost.
        temporal_preference:    FR-QR-07 — user's temporal reading fingerprint dict
                                with keys 'darkness_tolerance', 'emotional_intensity'.
    """
    active_user_prefs = {
        k: v
        for k, v in user_profile.model_dump().items()
        if v is not None and isinstance(v, (int, float))
    }

    for candidate in candidates:
        candidate.explanation_factors = []

        # 1. Base Vector Similarity (Max 0.30)
        vector_component = (
            candidate.base_vector_score or 0.0
        ) * WEIGHT_VECTOR_SIMILARITY

        # 2. Query-Trope Alignment (Max 0.15)
        query_trope_component = 0.0
        if query_trope_names and idf_weights and candidate.book_trope_names:
            qt_score = calculate_trope_overlap(
                query_trope_names,
                candidate.book_trope_names,
                idf_weights,
            )
            query_trope_component = qt_score * WEIGHT_QUERY_TROPE

        # 3. Tower 1 Profile Match (Max 0.25)
        # Non-narrative works (non-fiction) zero this component entirely.
        # Without the is_narrative gate, non-fiction books were receiving a free
        # 0.5 × 0.25 = 0.125 neutral bonus from _calculate_tower1_overlap's
        # empty-dict fallback — ranking them above genuinely matched fiction.
        if not candidate.is_narrative:
            tower1_component = 0.0
        else:
            tower1_score = _calculate_tower1_overlap(
                active_user_prefs, candidate.book_inferred_profile
            )
            tower1_component = tower1_score * WEIGHT_TOWER1_MATCH
            if tower1_score > 0.7:
                candidate.explanation_factors.append(
                    "Strong match with your core reading preferences."
                )

        # 4. TBR Context Bonus (Max 0.10)
        # B1 fix: bonus only fires when the book has genuine trope overlap with
        # the current query. A book saved under "dark romance" should not receive
        # the TBR bonus in an existentialism or gothic horror query even if it's
        # actively in the user's TBR.
        #
        # Three cases:
        #   a) query has no tropes OR book has no tropes → trope gate can't evaluate →
        #      grant the bonus (we can't penalise what we can't measure)
        #   b) query has tropes AND book has tropes AND overlap > 0 → grant bonus
        #   c) query has tropes AND book has tropes AND overlap == 0 → no bonus,
        #      clear the tbr badge so it doesn't show the "matched mood" explanation
        trope_gate_unevaluable = (
            not query_trope_names or not idf_weights or not candidate.book_trope_names
        )
        tbr_has_overlap = query_trope_component > 0.0

        if candidate.is_tbr_context_match and (
            trope_gate_unevaluable or tbr_has_overlap
        ):
            tbr_component = WEIGHT_TBR_BONUS
            candidate.match_source = "tbr"
            candidate.explanation_factors.append(
                "Matches the exact mood you were in when you added this to your TBR."
            )
        else:
            # Zero trope overlap — TBR book doesn't belong in this query context.
            # Clear the badge so the zero-overlap gate handles suppression cleanly.
            tbr_component = 0.0
            candidate.is_tbr_context_match = False

        # 4b. Interested Resurfacing Bonus (Max 0.05)
        # Counters the recency penalty for books the user explicitly soft-flagged.
        # Does not elevate to TBR level — just prevents penalty-stacking.
        interested_component = (
            WEIGHT_INTERESTED_BONUS if candidate.is_interested else 0.0
        )
        if candidate.is_interested and not candidate.explanation_factors:
            candidate.explanation_factors.append(
                "You flagged this as interesting before."
            )

        # 5. Community Buzz Score (Max 0.10)
        buzz_component = (candidate.community_buzz_score or 0.0) * WEIGHT_COMMUNITY_BUZZ

        # 5b. Temporal Boost (Max 0.05) — FR-QR-07
        temporal_component = 0.0
        if (
            current_hour is not None
            and day_of_week is not None
            and temporal_preference is not None
            and candidate.is_narrative
        ):
            temporal_component = (
                _calculate_temporal_boost(
                    current_hour,
                    day_of_week,
                    temporal_preference,
                    candidate.book_inferred_profile,
                )
                * WEIGHT_TEMPORAL
            )

        # 5c. Phase-based boost (Max 0.05) — FR-PH
        phase_component = 0.0
        if reader_phase and reader_phase.get("phase") == "genre_sprint":
            _sprint_genre = reader_phase.get("genre")
            if _sprint_genre and _sprint_genre in (candidate.book_trope_names or []):
                phase_component = 0.05

        # 6. Recency Penalty (Max -0.10)
        recency_component = PENALTY_RECENCY if candidate.seen_recently else 0.0

        raw_total = (
            vector_component
            + query_trope_component
            + tower1_component
            + tbr_component
            + interested_component
            + buzz_component
            + temporal_component
            + phase_component
            + recency_component
        )

        # 7. Zero-overlap gate (Issue 7 / FR-QR-05)
        # When the query has a clear canonical trope signal AND the candidate has
        # catalogued tropes AND none of them match, the book is almost certainly
        # in the wrong genre register. Apply a strong suppression multiplier.
        #
        # Conditions that bypass the gate (all must be false to trigger it):
        #   - query_trope_names is empty  → no query signal, gate can't fire
        #   - idf_weights is empty        → IDF not available, skip safely
        #   - candidate.book_trope_names is empty → book unenriched, pass through
        #   - overlap > 0                 → at least one matching trope, not gated
        gate_multiplier = 1.0
        if (
            query_trope_names
            and idf_weights
            and candidate.book_trope_names
            and query_trope_component == 0.0  # zero overlap already computed above
        ):
            gate_multiplier = 0.35
            logger.debug(
                f"Zero-overlap gate fired for '{candidate.title}' "
                f"(query tropes: {query_trope_names[:3]}, "
                f"book tropes: {candidate.book_trope_names[:3]})"
            )

        candidate.final_score = max(0.0, round(raw_total * gate_multiplier, 4))

        # 8. Anchor defining-trope multiplier (similarity queries only)
        # Separate from the zero-overlap gate — handles partial overlap cases where
        # the gate doesn't fire but the candidate is still in the wrong register.
        # anchor_defining_tropes contains the anchor book's confidence-1.0 tropes only.
        if anchor_defining_tropes and candidate.book_trope_names:
            _defining_set = set(anchor_defining_tropes)
            _book_set = set(candidate.book_trope_names)
            _matched_defining = _defining_set & _book_set

            if len(_matched_defining) == len(_defining_set):
                # All defining tropes present — strong match, boost
                _defining_multiplier = 1.4
            elif _matched_defining:
                # Partial defining trope match — neutral (already scored via IDF)
                _defining_multiplier = 1.0
            else:
                # Zero defining tropes — wrong register despite partial overlap
                _defining_multiplier = 0.6
                logger.debug(
                    f"Defining-trope penalty for '{candidate.title}': "
                    f"has none of {anchor_defining_tropes}"
                )

            candidate.final_score = max(
                0.0, round(candidate.final_score * _defining_multiplier, 4)
            )

        if not candidate.explanation_factors:
            candidate.explanation_factors.append(
                "Semantically matches your current mood query."
            )

    ranked_candidates = sorted(candidates, key=lambda c: c.final_score, reverse=True)

    logger.info(
        f"Reranked {len(ranked_candidates)} candidates. "
        f"Top score: {ranked_candidates[0].final_score if ranked_candidates else 0}"
    )
    return ranked_candidates


def _calculate_tower1_overlap(
    user_prefs: Dict[str, float], book_profile: Dict[str, float]
) -> float:
    """Normalized overlap between user long-term preferences and book Tower 1 values."""
    if not user_prefs or not book_profile:
        return 0.5
    shared_keys = set(user_prefs.keys()).intersection(set(book_profile.keys()))
    if not shared_keys:
        return 0.5
    total_similarity = sum(
        1.0 - abs(user_prefs[k] - book_profile[k]) for k in shared_keys
    )
    return total_similarity / len(shared_keys)


# ── IDF-weighted trope overlap ────────────────────────────────────────────────


def compute_trope_idf(db: Session) -> Dict[str, float]:
    """
    Compute IDF weights for all tropes: IDF = log(total_books / books_with_trope).

    High-frequency nodes (Internal Conflict: 78% of catalog) → near-zero weight.
    Rare, specific nodes (Dark Academia: 1%) → high weight.

    Call once per recommendation request. Cache the result keyed on TAXONOMY_VERSION
    once the catalog is large enough to make per-request computation slow.
    """
    total_books = db.execute(select(func.count()).select_from(Work)).scalar() or 1

    rows = db.execute(
        select(Trope.canonical_name, func.count(BookTrope.work_uuid).label("cnt"))
        .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
        .group_by(Trope.canonical_name)
    ).all()

    return {name: math.log(total_books / max(count, 1)) for name, count in rows}


def calculate_trope_overlap(
    user_trope_names: List[str],
    book_trope_names: List[str],
    idf_weights: Dict[str, float],
) -> float:
    """
    IDF-weighted trope overlap score between a trope list and a book.

    Used in two contexts:
    - Long-term: user_trope_names = tropes the user consistently engages with
    - Query-time: user_trope_names = tropes implied by the current query

    Returns 0.0–1.0. 0.0 if no shared tropes or empty inputs.
    """
    if not user_trope_names or not book_trope_names or not idf_weights:
        return 0.0

    shared = set(user_trope_names) & set(book_trope_names)
    if not shared:
        return 0.0

    score = sum(idf_weights.get(t, 0.0) for t in shared)
    max_possible = sum(idf_weights.get(t, 0.0) for t in user_trope_names)

    if max_possible <= 0:
        return 0.0

    return min(1.0, score / max_possible)


def _calculate_temporal_boost(
    current_hour: int,
    day_of_week: int,
    temporal_preference: Dict[str, float],
    book_profile: Dict[str, float],
) -> float:
    """
    FR-QR-07: Compute temporal reading pattern alignment (0.0–1.0).

    Compares the candidate book's darkness_tolerance and emotional_intensity
    against the user's typical reading pattern for this time slot.

    Late-night / weekend → boost darker, higher-emotional-intensity books.
    Morning → boost lighter, lower-intensity books.

    Returns 0.0 if the temporal fingerprint for this slot is empty
    (user has no reading history at this time).
    """
    if not temporal_preference or not book_profile:
        return 0.0

    slot_darkness = temporal_preference.get("darkness_tolerance")
    slot_emotional = temporal_preference.get("emotional_intensity")

    if slot_darkness is None and slot_emotional is None:
        return 0.0

    book_darkness = book_profile.get("darkness_tolerance", 0.5)
    book_emotional = book_profile.get("emotional_intensity", 0.5)

    similarity = 0.0
    keys_compared = 0

    if slot_darkness is not None:
        similarity += 1.0 - abs(slot_darkness - book_darkness)
        keys_compared += 1

    if slot_emotional is not None:
        similarity += 1.0 - abs(slot_emotional - book_emotional)
        keys_compared += 1

    return similarity / max(keys_compared, 1)
