import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user_uuid
from app.models.books import Work
from app.models.events import EventType, InteractionEvent
from app.models.tropes import BookTrope, Trope
from app.models.users import User, UserProfile
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
                "darkness_tolerance",
                "angst_level",
                "violence_tolerance",
                "speculative_deviation",
                "world_building_appetite",
                "plot_vs_character",
                "standalone_preference",
                "series_completion_tendency",
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

        dimensions.append(
            {
                "key": field,
                "name": labels.get(f"{_prefix}name", labels["name"]),
                "question": labels.get(f"{_prefix}question", labels["question"]),
                "value": value,
                "interpretation": interpretation,
            }
        )

    dimensions.sort(key=lambda d: abs(d["value"] - 0.5), reverse=True)
    from app.config import settings

    is_admin = not settings.ADMIN_USER_UUID or user_uuid == settings.ADMIN_USER_UUID
    phase = user_intelligence.detect_reader_phase(db, user_uuid)

    # FR-CS-03: Calculate user calibration progress
    user = db.execute(
        select(User).where(User.user_uuid == user_uuid)
    ).scalar_one_or_none()
    meaningful_events = [
        EventType.LOGGED_READ,
        EventType.NOT_INTERESTED,
        EventType.QUERY,
        EventType.TBR_ADD,
        EventType.INTERESTED,
        EventType.REREAD,
    ]
    interaction_count = (
        db.execute(
            select(func.count(InteractionEvent.event_uuid)).where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type.in_(meaningful_events),
            )
        ).scalar()
        or 0
    )

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


TIME_OF_DAY_LABELS: dict[str, str] = {
    "morning": "mornings",
    "afternoon": "afternoons",
    "evening": "evenings",
    "night": "late nights",
}

DAY_LABELS: dict[str, str] = {
    "Monday": "Mondays",
    "Tuesday": "Tuesdays",
    "Wednesday": "Wednesdays",
    "Thursday": "Thursdays",
    "Friday": "Fridays",
    "Saturday": "Saturdays",
    "Sunday": "Sundays",
}


@router.get("/rhythm")
def get_reading_rhythm(
    db: Session = Depends(get_db),
    user_uuid: str = Depends(get_current_user_uuid),
):
    """
    Returns temporal reading-pattern insights derived from interaction_events.
    No new data collection — purely analytical over existing timestamps.
    """
    read_types = [EventType.LOGGED_READ, EventType.REREAD]

    # ── 1.  Fetch all completed-read events with work + trope data ──
    events = (
        db.execute(
            select(InteractionEvent)
            .where(
                InteractionEvent.user_uuid == user_uuid,
                InteractionEvent.event_type.in_(read_types),
            )
            .order_by(InteractionEvent.event_timestamp.desc())
        )
        .scalars()
        .all()
    )

    if not events:
        return {
            "insights": [],
            "message": "Not enough reading data yet. Finish a book and come back — your rhythm will surface here.",
        }

    # ── 2.  Aggregate raw counts ──
    day_counter: Counter = Counter()
    tod_counter: Counter = Counter()
    today = datetime.now(timezone.utc).date()

    # Windowed: last 30 days for velocity, all-time for preferences
    recent_30 = 0
    recent_weekend = 0
    recent_weekday = 0
    # Trope-by-time-of-day
    trope_by_tod: dict[str, Counter] = defaultdict(Counter)

    # For binge detection
    dates_sorted: list[datetime] = []

    for e in events:
        ts = e.event_timestamp
        if ts is None:
            continue
        dates_sorted.append(ts)

        # Resolve time-of-day — prefer stored column, fall back to hour
        tod = e.time_of_day
        if not tod:
            hour = ts.hour
            if 5 <= hour < 12:
                tod = "morning"
            elif 12 <= hour < 17:
                tod = "afternoon"
            elif 17 <= hour < 22:
                tod = "evening"
            else:
                tod = "night"
        tod_counter[tod] += 1

        # Resolve day-of-week
        dow = e.day_of_week or ts.strftime("%A")
        day_counter[dow] += 1

        # Recent window
        days_ago = (today - ts.date()).days
        if days_ago <= 30:
            recent_30 += 1
            if dow in ("Saturday", "Sunday"):
                recent_weekend += 1
            else:
                recent_weekday += 1

        # ── Trope affinity by time-of-day ──
        if e.work_uuid:
            tropes = (
                db.execute(
                    select(Trope.canonical_name)
                    .join(BookTrope, BookTrope.trope_uuid == Trope.trope_uuid)
                    .where(BookTrope.work_uuid == e.work_uuid)
                )
                .scalars()
                .all()
            )
            for t in tropes:
                trope_by_tod[tod][t] += 1

    # ── 3.  Build insights ──
    insights: list[dict] = []

    # (a) Peak day
    if day_counter:
        peak_day, peak_day_count = day_counter.most_common(1)[0]
        total = sum(day_counter.values())
        pct = round(peak_day_count / total * 100)
        label = DAY_LABELS.get(peak_day, peak_day)
        insights.append(
            {
                "icon": "📅",
                "headline": f"Your peak reading day is {label}",
                "detail": f"{pct}% of your finished books land on {label.lower()}. That's your sweet spot.",
            }
        )

    # (b) Peak time-of-day
    if tod_counter:
        peak_tod, peak_tod_count = tod_counter.most_common(1)[0]
        total_tod = sum(tod_counter.values())
        pct_tod = round(peak_tod_count / total_tod * 100)
        label_tod = TIME_OF_DAY_LABELS.get(peak_tod, peak_tod)
        insights.append(
            {
                "icon": "🕐",
                "headline": f"You finish most books in the {label_tod}",
                "detail": f"{pct_tod}% of your completions happen during {label_tod}. Prime reading hours.",
            }
        )

    # (c) Weekend vs weekday pace (last 30 days)
    if recent_30 >= 3:
        # Normalize to per-day rate
        weekend_days_in_window = sum(
            1 for i in range(30) if (today - timedelta(days=i)).weekday() >= 5
        )
        weekday_days_in_window = 30 - weekend_days_in_window
        weekend_rate = recent_weekend / max(weekend_days_in_window, 1)
        weekday_rate = recent_weekday / max(weekday_days_in_window, 1)

        if weekend_rate > weekday_rate * 1.3:
            insights.append(
                {
                    "icon": "🏖️",
                    "headline": "You finish books faster on weekends",
                    "detail": (
                        f"Over the last 30 days, you've finished {recent_weekend} books on weekends "
                        f"vs {recent_weekday} on weekdays. Weekends are your reading engine."
                    ),
                }
            )
        elif weekday_rate > weekend_rate * 1.3:
            insights.append(
                {
                    "icon": "☕",
                    "headline": "You're a weekday reader",
                    "detail": (
                        f"{recent_weekday} books finished on weekdays vs {recent_weekend} on weekends "
                        f"in the last 30 days. Your reading lives in the workweek."
                    ),
                }
            )

    # (d) Trope affinity by time-of-day
    if trope_by_tod:
        # For each time bucket, find the top trope
        for tod_bucket in ("morning", "afternoon", "evening", "night"):
            counter = trope_by_tod.get(tod_bucket)
            if not counter or sum(counter.values()) < 2:
                continue
            top_trope, top_count = counter.most_common(1)[0]
            label_tod = TIME_OF_DAY_LABELS.get(tod_bucket, tod_bucket)
            insights.append(
                {
                    "icon": "🏷️",
                    "headline": f"You lean toward {top_trope} in the {label_tod}",
                    "detail": (
                        f"When you read during {label_tod}, '{top_trope}' is your most common flavour. "
                        f"Your mood has a clock."
                    ),
                }
            )
            break  # show the first non-empty bucket as the highlight

    # (e) Velocity — books per month
    dates_sorted.sort()
    if len(dates_sorted) >= 2:
        first = dates_sorted[0]
        last = dates_sorted[-1]
        span_days = max((last - first).days, 1)
        books_per_week = round(len(dates_sorted) / (span_days / 7), 1)
        books_per_month = round(books_per_week * 4.3, 1)
        insights.append(
            {
                "icon": "📚",
                "headline": f"You average {books_per_week} book{'s' if books_per_week != 1 else ''} per week",
                "detail": (
                    f"That's roughly {books_per_month} per month across {span_days} days of tracked reading. "
                    f"Steady pace."
                ),
            }
        )

    # (f) Binge detection — 3+ books in 7 days
    date_counts: Counter = Counter(d.date() for d in dates_sorted)
    binge_windows: list[str] = []
    for i in range(len(dates_sorted)):
        window_start = dates_sorted[i]
        window_end = window_start + timedelta(days=7)
        count = sum(1 for d in dates_sorted if window_start <= d <= window_end)
        if count >= 3:
            label = window_start.strftime("%b %d")
            if label not in binge_windows:
                binge_windows.append(label)
        if len(binge_windows) >= 2:
            break

    if binge_windows:
        insights.append(
            {
                "icon": "🔥",
                "headline": f"You had a reading binge around {binge_windows[0]}",
                "detail": (
                    f"3+ books finished within a single week. "
                    f"{'Another binge followed later.' if len(binge_windows) > 1 else 'A proper devouring.'}"
                ),
            }
        )

    if not insights:
        return {
            "insights": [],
            "message": "Not enough reading data yet. Finish a book and come back — your rhythm will surface here.",
        }

    return {"insights": insights}
