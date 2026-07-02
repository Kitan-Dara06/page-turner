import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import llm
from app.integrations.llm import LLM_UNAVAILABLE
from app.logging import log_entry_exit
from app.models.events import EventType
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
    from sqlalchemy import text as sa_text

    rows = (
        db.execute(sa_text("SELECT canonical_name FROM tropes ORDER BY canonical_name"))
        .scalars()
        .all()
    )
    return sorted(rows)


def _build_system_prompt(trope_names: List[str]) -> str:
    # Format as a compact comma-separated block (same token density as before,
    # but now sourced from the DB rather than a hardcoded string).
    trope_block = ", ".join(trope_names)
    return f"""\
You are the semantic orchestration core of PAGETURNER, a highly advanced contextual book recommendation engine.
Analyze a reader's raw natural language query and output strict JSON with EIGHT fields:

1. "intent": Exactly one of "lookup", "similarity", "departure", "discovery".
   - lookup: User wants to FIND a specific author or book. Only when asking WHO/WHERE.
   - similarity: User wants books SIMILAR to something they reference.
   - departure: User is DONE with something and wants DIFFERENT.
   - discovery: User describes a mood/vibe/genre without a reference point.

2. "intent_confidence": Float 0.0-1.0. Below 0.5 = ambiguous, system defaults to discovery.

3. "expanded_query": A string optimized for dense semantic vector database retrieval (Qdrant k-NN). Expand abbreviations, append specific sub-genres, cross-reference implied themes, and include standard publishing tropes.

4. "constraints": A JSON object of HARD GATES — books that don't satisfy these are EXCLUDED, not just scored lower.
   Keys (all boolean, all optional, all default false):
   - "standalone_only": true if user explicitly wants standalone/not-a-series/single-volume.
   - "completed_series_only": true if user wants a series where ALL books are published.
   - "no_ya": true if user explicitly says "not YA", "adult only", "no young adult".
   - "no_series": true if user wants to avoid series entirely (stronger than standalone_only).

5. "query_tropes": A list of canonical trope names this query implies. You MUST only use names from the CANONICAL TROPE LIST below — do not invent new names. These are GENRE/TROPE REQUESTS (e.g. "Why Choose", "Enemies to Lovers"), not emotional descriptors. Maximum 8 tropes. Return [] if no specific tropes are implied.

6. "preferences": A JSON object of SOFT PREFERENCES — these boost candidate scores but don't exclude. Only include dimensions the user explicitly mentions or strongly implies. Keys must be from the VALID TOWER 1 KEYS list below. Values are 0.0-1.0.
   Use >0.7 for strong preference, 0.4-0.7 for mild preference. Do NOT include keys the user doesn't mention.

7. "vibe": A short phrase (5-15 words) capturing the pure emotional/compositional CORE of what the user wants. This drives the vector search direction. Strip constraints and trope names — this is pure VIBE. Examples:
   - Query: "standalone why choose dark romance" → vibe: "intense polyamorous dark romance with emotional devastation"
   - Query: "cozy fantasy with tea shops and no violence" → vibe: "warm gentle fantasy about community and comfort"
   - Query: "books that will destroy me emotionally like A Little Life" → vibe: "devastating literary tragedy about suffering and endurance"

8. "anchor_author": If the query mentions a specific author by name, extract the author's full name. Return null if no specific author.

CANONICAL TROPE LIST (use ONLY these exact strings):
{trope_block}

VALID TOWER 1 KEYS (for preferences only):
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
- explicit_content_level (0.0=clean/fade-to-black, 1.0=highly explicit)
- romance_centrality (0.0=no romance, 1.0=romance is the primary engine)
- hea_requirement (0.0=tragedy acceptable, 1.0=Happily Ever After mandatory)

RULES:
- Return valid JSON matching the specified structure exactly.
- Do not invent Tower 1 keys or trope names.
- If a Tower 1 parameter isn't mentioned or implied, do NOT include it in preferences.
- For constraints, only set true when the user EXPLICITLY states the requirement. Do not infer.
- Vibe must NOT include trope names — those go in query_tropes. Vibe is pure mood.
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
    """Build reader context using raw SQL to avoid ORM mapper issues."""
    from sqlalchemy import text as sa_text

    parts = []

    # Recently read titles
    rids = (
        db.execute(
            sa_text(
                "SELECT work_uuid FROM interaction_events "
                "WHERE user_uuid = :uid AND event_type = 'logged_read' "
                "ORDER BY event_timestamp DESC LIMIT 3"
            ),
            {"uid": user_uuid},
        )
        .scalars()
        .all()
    )
    if rids:
        titles = (
            db.execute(
                sa_text("SELECT title FROM works WHERE work_uuid = ANY(:wids)"),
                {"wids": rids},
            )
            .scalars()
            .all()
        )
        if titles:
            parts.append(f"Recently read: {', '.join(titles)}")

    # Recent queries
    rqs = (
        db.execute(
            sa_text(
                "SELECT query_text FROM interaction_events "
                "WHERE user_uuid = :uid AND event_type = 'query' "
                "AND query_text IS NOT NULL "
                "ORDER BY event_timestamp DESC LIMIT 3"
            ),
            {"uid": user_uuid},
        )
        .scalars()
        .all()
    )
    if rqs:
        parts.append(f"Recent queries: {' | '.join(q[:80] for q in rqs)}")

    # Active TBR
    tbr_wids = (
        db.execute(
            sa_text(
                "SELECT work_uuid FROM tbr_entries "
                "WHERE user_uuid = :uid AND status = 'active' "
                "ORDER BY priority_score DESC LIMIT 5"
            ),
            {"uid": user_uuid},
        )
        .scalars()
        .all()
    )
    if tbr_wids:
        tbr_titles = (
            db.execute(
                sa_text("SELECT title FROM works WHERE work_uuid = ANY(:wids)"),
                {"wids": tbr_wids},
            )
            .scalars()
            .all()
        )
        if tbr_titles:
            parts.append(f"Active TBR: {', '.join(tbr_titles[:5])}")

    # Taste profile
    profile_cols = [
        "darkness_tolerance",
        "angst_level",
        "violence_tolerance",
        "thematic_density",
        "pacing_preference",
        "prose_density",
        "narrative_linearity",
        "plot_vs_character",
        "setting_scope",
        "speculative_deviation",
        "world_building_appetite",
        "emotional_intensity",
        "standalone_preference",
        "explicit_content_level",
        "romance_centrality",
        "hea_requirement",
    ]
    row = db.execute(
        sa_text(
            f"SELECT {', '.join(profile_cols)} FROM user_profiles WHERE user_uuid = :uid"
        ),
        {"uid": user_uuid},
    ).fetchone()
    if row:
        active = {}
        for i, col in enumerate(profile_cols):
            v = row[i]
            if v is not None and v > 0.6:
                active[col] = float(v)
        if active:
            t1_str = ", ".join(
                f"{k.replace('_', ' ')}:{v:.2f}" for k, v in active.items()
            )
            parts.append(f"Taste profile: {t1_str}")
    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Structured output types
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class QueryConstraints:
    standalone_only: bool = False
    completed_series_only: bool = False
    no_ya: bool = False
    no_series: bool = False

    def any_active(self) -> bool:
        return any(
            [
                self.standalone_only,
                self.completed_series_only,
                self.no_ya,
                self.no_series,
            ]
        )

    def exclusionary_only(self) -> "QueryConstraints":
        """Return a copy with only non-relaxable exclusions."""
        return QueryConstraints(no_ya=self.no_ya)

    def structural_only(self) -> "QueryConstraints":
        """Return a copy with only relaxable structural constraints."""
        return QueryConstraints(
            standalone_only=self.standalone_only,
            completed_series_only=self.completed_series_only,
            no_series=self.no_series,
        )


_BOUNDARY_KEYS = {"violence_tolerance", "darkness_tolerance", "explicit_content_level"}


@dataclass
class QueryIntent:
    intent: str = "discovery"
    expanded_query: str = ""
    vibe: str = ""  # pure mood — drives Qdrant vector search
    constraints: QueryConstraints = field(default_factory=QueryConstraints)
    query_tropes: List[str] = field(default_factory=list)
    unmatched_tropes: List[str] = field(
        default_factory=list
    )  # LLM output not in canonical list
    preferences_atmospheric: Dict[str, float] = field(default_factory=dict)
    preferences_boundary: Dict[str, float] = field(default_factory=dict)
    anchor_author: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@log_entry_exit()
def process_reader_query(db: Session, user_uuid: str, raw_query: str) -> QueryIntent:
    """
    Orchestrates the conversion of a raw string query into structured search
    parameters with four distinct buckets:
      - constraints: hard gates (standalone_only, no_ya, etc.)
      - query_tropes: genre/trope filters (must-match for Qdrant)
      - preferences: soft scoring (split into atmospheric vs boundary)
      - vibe: pure mood direction for Qdrant vector search

    Unmatched tropes are written to orphan_queue and returned in the result
    so the explanation layer can surface honest messaging.
    """
    logger.info(f"Processing query for user {user_uuid}: '{raw_query[:80]}...'")

    def _fallback():
        return QueryIntent(
            intent="discovery",
            expanded_query=raw_query,
            vibe=raw_query,
        )

    system_prompt = _get_system_prompt(db)
    ctx = _build_context_block(db, user_uuid)
    if ctx:
        prompt = (
            f"Reader context:\n{ctx}\n\n"
            f'User raw query: "{raw_query}"\n\n'
            "Classify intent using the reader context. "
            "Output strict JSON:"
        )
    else:
        prompt = f'User raw query: "{raw_query}"\n\nOutput strict JSON:'

    try:
        response_json = llm.complete(
            prompt=prompt, system=system_prompt, require_json=True
        )
        if (
            response_json == LLM_UNAVAILABLE
            or response_json is None
            or not isinstance(response_json, dict)
        ):
            logger.warning("LLM unavailable — using raw query as fallback.")
            return _fallback()
    except Exception as e:
        logger.error(f"LLM query expansion failed: {e}. Falling back.")
        return _fallback()

    # 0. Intent + confidence
    intent = (response_json.get("intent") or "discovery").strip().lower()
    if intent not in ("lookup", "similarity", "departure", "discovery"):
        intent = "discovery"
    confidence = float(response_json.get("intent_confidence", 0.5))
    if confidence < 0.5:
        intent = "discovery"
    logger.info(f"Intent: {intent} (confidence={confidence:.2f})")

    # 1. Expanded query
    expanded_query = response_json.get("expanded_query", raw_query)

    # 2. Constraints
    raw_cons = response_json.get("constraints", {}) or {}
    constraints = QueryConstraints(
        standalone_only=bool(raw_cons.get("standalone_only", False)),
        completed_series_only=bool(raw_cons.get("completed_series_only", False)),
        no_ya=bool(raw_cons.get("no_ya", False)),
        no_series=bool(raw_cons.get("no_series", False)),
    )

    # 3. Query tropes — validate against canonical list
    known_tropes = set(_CANONICAL_TROPE_NAMES or [])
    raw_tropes = response_json.get("query_tropes", []) or []
    query_trope_names: List[str] = []
    unmatched_tropes: List[str] = []
    for t in raw_tropes:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        if t in known_tropes:
            if t not in query_trope_names:
                query_trope_names.append(t)
        else:
            unmatched_tropes.append(t)
            # Write to orphan_queue so repeated queries surface the gap
            _write_query_orphan(db, t)
    query_trope_names = query_trope_names[:8]
    unmatched_tropes = unmatched_tropes[:8]
    if unmatched_tropes:
        logger.info(f"Unmatched query tropes → orphan_queue: {unmatched_tropes}")

    # 4. Preferences — split atmospheric vs boundary
    raw_prefs = response_json.get("preferences", {}) or {}
    prefs_atmospheric: Dict[str, float] = {}
    prefs_boundary: Dict[str, float] = {}
    valid_t1 = (
        Tower1Profile.model_fields.keys()
        if hasattr(Tower1Profile, "model_fields")
        else []
    )
    for key, val in raw_prefs.items():
        if key not in valid_t1 or not isinstance(val, (int, float)):
            continue
        v = round(max(0.0, min(1.0, float(val))), 4)
        if v == 0.5:
            continue  # neutral — skip
        if key in _BOUNDARY_KEYS:
            prefs_boundary[key] = v
        else:
            prefs_atmospheric[key] = v

    # 5. Vibe — pure mood for Qdrant
    vibe = (response_json.get("vibe") or raw_query).strip()

    # 6. Anchor author
    anchor_author = response_json.get("anchor_author") or None
    if anchor_author:
        anchor_author = str(anchor_author).strip() or None

    # Apply Tower 1 delta from preferences (only atmospheric — boundaries are
    # not applied as permanent profile changes, they're query-time dampeners)
    if prefs_atmospheric:
        try:
            user_intelligence.apply_tower1_delta(
                db=db,
                user_uuid=user_uuid,
                delta=prefs_atmospheric,
                trigger_event=EventType.QUERY.value,
            )
            logger.info(f"Profile delta applied: {list(prefs_atmospheric.keys())}")
        except Exception as e:
            logger.error(f"Failed to commit profile delta: {e}")

    return QueryIntent(
        intent=intent,
        expanded_query=expanded_query,
        vibe=vibe,
        constraints=constraints,
        query_tropes=query_trope_names,
        unmatched_tropes=unmatched_tropes,
        preferences_atmospheric=prefs_atmospheric,
        preferences_boundary=prefs_boundary,
        anchor_author=anchor_author,
    )


def _write_query_orphan(db: Session, tag: str):
    """Write an unmatched query-level trope to orphan_queue for gap detection."""
    from sqlalchemy import text as sa_text

    try:
        db.execute(
            sa_text(
                "INSERT INTO orphan_queue (tag_text, source, frequency_count, first_seen, last_seen) "
                "VALUES (:tag, 'query_extraction', 1, now(), now()) "
                "ON CONFLICT (tag_text) DO UPDATE SET frequency_count = orphan_queue.frequency_count + 1, last_seen = now()"
            ),
            {"tag": tag.lower().strip()},
        )
        db.commit()
    except Exception:
        db.rollback()
