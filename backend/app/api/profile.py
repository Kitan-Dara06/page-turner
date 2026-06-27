import logging

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.users import User, UserProfile
from app.models.events import EventType, InteractionEvent
from app.services import user_intelligence

logger = logging.getLogger(__name__)
router = APIRouter()

# Plain-language labels for each Tower 1 dimension.
# High (close to 1.0) and low (close to 0.0) interpretations.
DIMENSION_LABELS = {
    "darkness_tolerance": {
        "name": "Darkness Tolerance",
        "question": "How dark do you like your stories?",
        "high": "You're drawn to morally grey worlds, bleak tones, and unflinching narratives. Happy endings are optional.",
        "low": "You prefer stories with hope, warmth, and a sense that things will work out.",
    },
    "angst_level": {
        "name": "Emotional Angst",
        "question": "How much emotional turmoil do you enjoy?",
        "high": "You seek out gut-wrenching emotional arcs, longing, and internal suffering. Bring on the pain.",
        "low": "You prefer lighter emotional registers — conflict without devastation.",
    },
    "violence_tolerance": {
        "name": "Violence Tolerance",
        "question": "How much on-page violence are you comfortable with?",
        "high": "You're fine with graphic combat, body horror, and unflinching depictions of violence.",
        "low": "You prefer violence off-page or implied. Gore isn't your thing.",
    },
    "thematic_density": {
        "name": "Thematic Density",
        "nf_name": "Subject Depth",
        "question": "How much intellectual weight do you want?",
        "nf_question": "Academic rigor or popular survey?",
        "high": "You read for ideas — layered symbolism, philosophical depth, books that reward re-reading.",
        "low": "You read for story first. Clarity and momentum over allegory.",
        "nf_high": "You prefer academic rigor — primary sources, dense argumentation, specialist depth.",
        "nf_low": "You prefer accessible surveys — clear explanations, narrative non-fiction, popular science.",
    },
    "pacing_preference": {
        "name": "Pacing",
        "nf_name": "Information Pace",
        "question": "Fast-paced or slow burn?",
        "nf_question": "Dense paragraphs or breezy chapters?",
        "high": "You love a slow build — atmospheric, immersive, taking time to steep.",
        "low": "You want momentum. Quick chapters, propulsive plotting, no filler.",
        "nf_high": "You're comfortable with dense, information-rich paragraphs that reward slow reading.",
        "nf_low": "You prefer breezy, chapter-a-sitting pacing — clear takeaways, minimal density.",
    },
    "prose_density": {
        "name": "Prose Style",
        "nf_name": "Accessibility",
        "question": "Sparse prose or lyrical richness?",
        "nf_question": "Specialist language or plain English?",
        "high": "You love language — lyrical, stylised prose that's a pleasure to read for its own sake.",
        "low": "You prefer transparent prose that gets out of the way. Story beats style.",
        "nf_high": "You're comfortable with specialist terminology and academic prose.",
        "nf_low": "You prefer plain English — concepts explained clearly without jargon.",
    },
    "emotional_intensity": {
        "name": "Emotional Intensity",
        "nf_name": "Narrative Engagement",
        "question": "How emotionally intense do you want your reading?",
        "nf_question": "Immersive storytelling or clinical reporting?",
        "high": "You want books that leave you wrecked — raw, visceral, unforgettable feelings.",
        "low": "You prefer emotional restraint. Moving without being overwhelming.",
        "nf_high": "You want narrative non-fiction that reads like a novel — immersive, character-driven, emotionally resonant.",
        "nf_low": "You prefer clinical, objective reporting — facts over narrative arc.",
    },
    "narrative_linearity": {
        "name": "Narrative Structure",
        "nf_name": "Structure",
        "question": "Linear storytelling or puzzle-box structure?",
        "nf_question": "Linear argument or essayistic exploration?",
        "high": "You enjoy non-linear narratives, flashbacks, dual timelines, and experimental structure.",
        "low": "You prefer stories told in order — clear, chronological, easy to follow.",
        "nf_high": "You enjoy essayistic, thematic structures — ideas explored from multiple angles.",
        "nf_low": "You prefer clear, linear arguments with a defined thesis and supporting evidence.",
    },
    "setting_scope": {
        "name": "Setting Scope",
        "nf_name": "Scope",
        "question": "Intimate focus or sweeping scale?",
        "nf_question": "Deep dive on one topic or broad survey?",
        "high": "You want epic scope — continents, centuries, multiple factions and worlds.",
        "low": "You prefer intimate, contained settings with a tight focus.",
        "nf_high": "You want a broad survey — centuries of history, global perspective, interdisciplinary scope.",
        "nf_low": "You prefer a deep dive on a single topic, person, or event.",
    },
    "speculative_deviation": {
        "name": "Speculative Deviation",
        "question": "How far from reality do you like to go?",
        "high": "You love the strange and the impossible — deep sci-fi, high fantasy, surrealism.",
        "low": "You prefer grounded, realistic stories. Minimal or no speculative elements.",
    },
    "world_building_appetite": {
        "name": "World-Building Appetite",
        "question": "How much invented world detail do you enjoy?",
        "high": "Give you maps, magic systems, invented languages, historical appendices.",
        "low": "You're fine with just enough world to serve the story — no lore dumps.",
    },
    "emotional_intensity": {
        "name": "Emotional Intensity",
        "question": "How emotionally intense do you want your reading?",
        "high": "You want books that leave you wrecked — raw, visceral, unforgettable feelings.",
        "low": "You prefer emotional restraint. Moving without being overwhelming.",
    },
    "standalone_preference": {
        "name": "Standalone Preference",
        "question": "Standalones or series?",
        "high": "You prefer complete-in-one books. No cliffhangers, no waiting for the next volume.",
        "low": "You love a series — immersion over multiple books, returning to familiar worlds.",
    },
    "series_completion_tendency": {
        "name": "Series Completion",
        "question": "Do you finish what you start?",
        "high": "When you start a series, you're likely to see it through to the end.",
        "low": "You're happy to read book one and move on. Completion isn't a priority.",
    },
}


@router.get("/")
def get_profile(
    content_mode: str = "fiction",
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """Returns the user's Tower 1 profile with plain-language interpretations."""
    profile = db.execute(
        select(UserProfile).where(UserProfile.user_uuid == user_uuid)
    ).scalar_one_or_none()

    if not profile:
        return {"dimensions": [], "message": "Not enough data yet — keep reading."}

    dimensions = []
    for field, labels in DIMENSION_LABELS.items():
        value = getattr(profile, field, None)
        if content_mode == "nonfiction":
            if field in (
                "darkness_tolerance", "angst_level", "violence_tolerance",
                "speculative_deviation", "world_building_appetite",
                "plot_vs_character", "standalone_preference", "series_completion_tendency",
            ):
                continue
            if value is None:
                continue
        else:
            if value is None:
                continue

        _prefix = "nf_" if content_mode == "nonfiction" else ""
        if value >= 0.6:
            interpretation = labels.get(f"{_prefix}high", labels["high"])
        elif value <= 0.4:
            interpretation = labels.get(f"{_prefix}low", labels["low"])
        else:
            interpretation = "You're somewhere in the middle on this — open to either direction depending on the book."

        dimensions.append({
            "key": field,
            "name": labels.get(f"{_prefix}name", labels["name"]),
            "question": labels.get(f"{_prefix}question", labels["question"]),
            "value": value,
            "interpretation": interpretation,
        })

    dimensions.sort(key=lambda d: abs(d["value"] - 0.5), reverse=True)
    from app.config import settings
    is_admin = not settings.ADMIN_USER_UUID or user_uuid == settings.ADMIN_USER_UUID
    phase = user_intelligence.detect_reader_phase(db, user_uuid)

    # FR-CS-03: Calculate user calibration progress
    user = db.execute(select(User).where(User.user_uuid == user_uuid)).scalar_one_or_none()
    meaningful_events = [
        EventType.LOGGED_READ,
        EventType.NOT_INTERESTED,
        EventType.QUERY,
        EventType.TBR_ADD,
        EventType.INTERESTED,
        EventType.REREAD,
    ]
    interaction_count = db.execute(
        select(func.count(InteractionEvent.event_uuid))
        .where(
            InteractionEvent.user_uuid == user_uuid,
            InteractionEvent.event_type.in_(meaningful_events)
        )
    ).scalar() or 0

    created_at = user.created_at if user else datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    days_since_signup = (now - created_at).days
    days_remaining = max(0, 30 - days_since_signup)
    interactions_remaining = max(0, 20 - interaction_count)
    calibration_complete = (days_remaining <= 0) or (interactions_remaining <= 0)

    if user and user.calibration_complete != calibration_complete:
        user.calibration_complete = calibration_complete
        db.commit()

    calibration_data = {
        "complete": calibration_complete,
        "days_remaining": days_remaining,
        "interactions_remaining": interactions_remaining,
        "total_interactions": interaction_count,
    }

    return {
        "dimensions": dimensions,
        "phase": phase,
        "is_admin": is_admin,
        "calibration": calibration_data,
    }
