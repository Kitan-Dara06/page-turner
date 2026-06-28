import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import llm
from app.integrations.llm import LLM_UNAVAILABLE
from app.logging import log_entry_exit
from app.models.events import EventType, InteractionEvent
from app.models.tbr import TBREntry, TBRStatus
from app.models.users import UserProfile
from app.schemas.users import Tower1Profile
from app.services import user_intelligence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
# The canonical trope list is loaded once per process from the DB so the
# prompt always reflects the live taxonomy — no hardcoded drift.
# _CANONICAL_TROPE_NAMES is populated lazily on the first call to
# _get_system_prompt() and reused for the lifetime of the process.
_CANONICAL_TROPE_NAMES: Optional[List[str]] = None


def _load_canonical_tropes(db: Session) -> List[str]:
    """Single DB round-trip — returns sorted canonical trope names."""
    from app.models.tropes import Trope

    rows = db.execute(select(Trope.canonical_name)).scalars().all()
    return sorted(rows)


def _build_system_prompt(trope_names: List[str]) -> str:
    # Format as a compact comma-separated block (same token density as before,
    # but now sourced from the DB rather than a hardcoded string).
    trope_block = ", ".join(trope_names)
    return f"""\
You are the semantic orchestration core of PAGETURNER, a highly advanced contextual book recommendation engine.
Analyze a reader's raw natural language query and output strict JSON with SIX fields:

1. "intent": Exactly one of "lookup", "similarity", "departure", "discovery".
   - lookup: User wants to FIND a specific author or book. Only when asking WHO/WHERE.
   - similarity: User wants books SIMILAR to something they reference.
   - departure: User is DONE with something and wants DIFFERENT.
   - discovery: User describes a mood/vibe/genre without a reference point.

2. "intent_confidence": Float 0.0-1.0. Below 0.5 = ambiguous, system defaults to discovery.

3. "expanded_query": A string optimized for dense semantic vector database retrieval (Qdrant k-NN). Expand abbreviations, append specific sub-genres, cross-reference implied themes, and include standard publishing tropes.

4. "tower1_delta": A precise float dictionary (0.0 to 1.0) indicating adjustments to the reader's explicit behavioral model (Tower 1). Only include keys that are directly or strongly implied by the emotional tone, pacing desires, or content limits of the text.

5. "query_tropes": A list of canonical trope names this query implies. You MUST only use names from the CANONICAL TROPE LIST below — do not invent new names. Maximum 8 tropes. Return [] if no specific tropes are implied.

CANONICAL TROPE LIST (use ONLY these exact strings):
{trope_block}

6. "anchor_author": If the query mentions a specific author by name (e.g. "books like X by Jane Smith"), extract the author's full name as a string. Return null if no specific author is mentioned.

VALID TOWER 1 KEYS:
- darkness_tolerance (0.0=cozy/light, 1.0=grimdark/extreme)
- angst_level (0.0=low conflict, 1.0=emotionally devastating)
- violence_tolerance (0.0=none, 1.0=graphic)
- thematic_density (0.0=popcorn read, 1.0=heavy philosophical/literary)
- pacing_preference (0.0=ultra slow burn/slice of life, 1.0=breakneck action)
- prose_density (0.0=transparent/simple, 1.0=purple/ornate)
- narrative_linearity (0.0=strictly chronological, 1.0=complex non-linear/nested)
- plot_vs_character (0.0=purely plot-driven, 1.0=purely character study)
- setting_scope (0.0=intimate/single room, 1.0=epic world-building)
- speculative_deviation (0.0=grounded reality, 1.0=high fantasy/hard sci-fi)
- emotional_intensity (0.0=detached, 1.0=cathartic/visceral)
- standalone_preference (0.0=epic multi-book series, 1.0=standalone single volume)
- explicit_content_level (0.0=clean/fade-to-black, 1.0=highly explicit)
- romance_centrality (0.0=no romance, 1.0=romance is the primary engine)
- hea_requirement (0.0=tragedy acceptable, 1.0=Happily Ever After mandatory)

RULES:
- Return valid JSON matching the specified structure exactly.
- Do not invent Tower 1 keys.
- If a Tower 1 parameter isn't mentioned or implied, do NOT include it.
- For query_tropes, ONLY use names from the CANONICAL TROPE LIST above.
"""


def _get_system_prompt(db: Session) -> str:
    """
    Returns the fully assembled system prompt, lazy-loading the canonical trope
    list from the DB on the first call and caching it for the process lifetime.

    The cache is intentionally process-scoped (not request-scoped). Taxonomy
    changes take effect on the next process restart, which is the right
    trade-off: zero per-request overhead vs. eventual consistency on rare
    taxonomy updates.
    """
    global _CANONICAL_TROPE_NAMES
    if _CANONICAL_TROPE_NAMES is None:
        _CANONICAL_TROPE_NAMES = _load_canonical_tropes(db)
        logger.info(
            f"Canonical trope list loaded: {len(_CANONICAL_TROPE_NAMES)} tropes"
        )
    return _build_system_prompt(_CANONICAL_TROPE_NAMES)


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------


def _build_context_block(db: Session, user_uuid: str) -> str:
    from app.models.books import Work

    parts = []
    rids = (
        db.execute(
            select(InteractionEvent.work_uuid)
            .where(InteractionEvent.user_uuid == user_uuid)
            .where(InteractionEvent.event_type == EventType.LOGGED_READ)
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(3)
        )
        .scalars()
        .all()
    )
    if rids:
        titles = (
            db.execute(select(Work.title).where(Work.work_uuid.in_(rids)))
            .scalars()
            .all()
        )
        if titles:
            parts.append(f"Recently read: {', '.join(titles)}")
    rqs = (
        db.execute(
            select(InteractionEvent.query_text)
            .where(InteractionEvent.user_uuid == user_uuid)
            .where(InteractionEvent.event_type == EventType.QUERY)
            .where(InteractionEvent.query_text.isnot(None))
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(3)
        )
        .scalars()
        .all()
    )
    if rqs:
        parts.append(f"Recent queries: {' | '.join(q[:80] for q in rqs)}")
    tbr_wids = (
        db.execute(
            select(TBREntry.work_uuid)
            .where(TBREntry.user_uuid == user_uuid)
            .where(TBREntry.status == TBRStatus.ACTIVE)
            .order_by(TBREntry.priority_score.desc())
            .limit(5)
        )
        .scalars()
        .all()
    )
    if tbr_wids:
        tbr_titles = (
            db.execute(select(Work.title).where(Work.work_uuid.in_(tbr_wids)))
            .scalars()
            .all()
        )
        if tbr_titles:
            parts.append(f"Active TBR: {', '.join(tbr_titles[:5])}")
    profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one_or_none()
    if profile:
        t1 = Tower1Profile.model_validate(profile)
        active = {k: v for k, v in t1.model_dump().items() if v is not None and v > 0.6}
        if active:
            t1_str = ", ".join(
                f"{k.replace('_', ' ')}:{v:.2f}" for k, v in active.items()
            )
            parts.append(f"Taste profile: {t1_str}")
    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@log_entry_exit()
def process_reader_query(
    db: Session, user_uuid: str, raw_query: str
) -> Tuple[str, Dict[str, float], List[str], Optional[str], str]:
    """
    Orchestrates the conversion of a raw string query into search parameters,
    then automatically applies the Tower 1 delta to the user's permanent profile.

    Returns:
        Tuple of:
        - expanded_query: str
        - cleaned_mood_tags_delta: Dict[str, float]
        - query_trope_names: List[str]   — canonical tropes implied by the query
        - anchor_author: Optional[str]   — author extracted from similarity queries
    """
    logger.info(f"Processing query for user {user_uuid}: '{raw_query[:60]}...'")

    system_prompt = _get_system_prompt(db)
    ctx = _build_context_block(db, user_uuid)
    if ctx:
        prompt = (
            f"Reader context:\n{ctx}\n\n"
            f'User raw query: "{raw_query}"\n\n'
            "Classify intent using the reader context — e.g. if they just "
            "finished a series and say 'need more like it', that's similarity "
            "NOT lookup. 'Done with this, something else' is departure.\n\n"
            "Output strict JSON:"
        )
    else:
        prompt = f'User raw query: "{raw_query}"\n\nOutput strict JSON:'

    try:
        response_json = llm.complete(
            prompt=prompt, system=system_prompt, require_json=True
        )
        # LLM timed out or returned sentinel — fall back to direct vector search
        if (
            response_json == LLM_UNAVAILABLE
            or response_json is None
            or not isinstance(response_json, dict)
        ):
            logger.warning(
                "LLM unavailable for query rewrite — using raw query as fallback."
            )
            return raw_query, {}, [], None, "discovery"
    except Exception as e:
        logger.error(
            f"LLM query expansion failed: {e}. Falling back to clean defaults."
        )
        return raw_query, {}, [], None, "discovery"

    # 0. Intent + confidence
    intent = (response_json.get("intent") or "discovery").strip().lower()
    if intent not in ("lookup", "similarity", "departure", "discovery"):
        intent = "discovery"
    confidence = float(response_json.get("intent_confidence", 0.5))
    if confidence < 0.5:
        logger.info(
            f"Low intent confidence ({confidence:.2f}), defaulting to discovery"
        )
        intent = "discovery"
    logger.info(f"Intent: {intent} (confidence={confidence:.2f})")

    # 1. Expanded query
    expanded_query = response_json.get("expanded_query", raw_query)

    # 2. Tower 1 delta — sanitize against valid Pydantic fields
    raw_delta = response_json.get("tower1_delta", {})
    cleaned_delta = {}
    valid_fields = (
        Tower1Profile.model_fields.keys()
        if hasattr(Tower1Profile, "model_fields")
        else []
    )
    for key, val in raw_delta.items():
        if key in valid_fields and isinstance(val, (int, float)):
            cleaned_delta[key] = round(max(0.0, min(1.0, float(val))), 4)

    # 3. Query tropes — validate against the canonical list that was used to
    # build the prompt. This is a second-pass filter in case the LLM hallucinates
    # despite explicit instructions. Unknown names are silently dropped.
    raw_tropes = response_json.get("query_tropes", [])
    known_tropes = set(_CANONICAL_TROPE_NAMES or [])
    query_trope_names = [
        t.strip()
        for t in raw_tropes
        if isinstance(t, str) and t.strip() in known_tropes
    ][:8]

    # 4. Anchor author
    anchor_author = response_json.get("anchor_author") or None
    if anchor_author:
        anchor_author = str(anchor_author).strip() or None

    # Apply delta to user profile
    if cleaned_delta:
        try:
            user_intelligence.apply_tower1_delta(
                db=db,
                user_uuid=user_uuid,
                delta=cleaned_delta,
                trigger_event=EventType.QUERY.value,
            )
            logger.info(
                f"Profile delta applied for {user_uuid}: {list(cleaned_delta.keys())}"
            )
        except Exception as e:
            logger.error(f"Failed to commit profile delta: {e}. Proceeding anyway.")

    return expanded_query, cleaned_delta, query_trope_names, anchor_author, intent
