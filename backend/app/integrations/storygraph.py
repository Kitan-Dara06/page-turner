"""
Community Tag Extraction — via Tavily search

StoryGraph tags are JavaScript-rendered and invisible to crawlers.
Instead, we search Tavily against Goodreads, Amazon, and BookTok-adjacent
content where community tags (moods, tropes, warnings) appear in review
snippets and book descriptions.

Tags feed directly into the LLM enrichment extraction prompt as context.
"""

import logging
from typing import Any, Dict, List, Optional

from app.integrations import tavily

logger = logging.getLogger(__name__)

# Mood vocabulary
MOODS = {
    "adventurous",
    "challenging",
    "dark",
    "emotional",
    "funny",
    "hopeful",
    "inspiring",
    "lighthearted",
    "mysterious",
    "reflective",
    "sad",
    "tense",
    "dramatic",
    "suspenseful",
    "romantic",
    "steamy",
    "spicy",
    "angsty",
}

# Pace vocabulary
PACE = {"slow-paced", "medium-paced", "fast-paced", "slow burn"}

# Content warnings
WARNINGS = [
    "violence",
    "stalking",
    "abuse",
    "torture",
    "kidnapping",
    "graphic",
    "explicit",
    "trauma",
    "death",
    "gore",
    "assault",
    "self-harm",
    "suicide",
    "grief",
]

# High-frequency romance community tropes
TROPES = {
    "dark romance",
    "contemporary romance",
    "historical romance",
    "paranormal romance",
    "sports romance",
    "mm romance",
    "ff romance",
    "romantic comedy",
    "romantasy",
    "enemies to lovers",
    "friends to lovers",
    "fake dating",
    "forced proximity",
    "slow burn",
    "second chance",
    "grumpy sunshine",
    "love triangle",
    "age gap",
    "billionaire romance",
    "mafia romance",
    "stalker romance",
    "bully romance",
    "dark academia",
    "reverse harem",
    "touch her and die",
    "possessive hero",
    "alpha hero",
    "morally grey",
    "anti-hero",
    "workplace romance",
    "small town romance",
    "holiday romance",
    "surprise pregnancy",
    "single parent",
    "marriage of convenience",
    "bodyguard romance",
    "brothers best friend",
    "hurt/comfort",
    "cozy romance",
    "instalove",
    "office romance",
    "royal romance",
    "captive romance",
    "dubcon",
    "fated mates",
    "shifter romance",
    "vampire romance",
    "werewolf romance",
    "fae romance",
    "omegaverse",
    "why choose",
    "bdsm",
    "spicy",
    "steamy",
    "motorcycle club",
    "rock star romance",
}


def fetch_tags(title: str, author: str) -> Optional[Dict[str, Any]]:
    """
    Search Tavily for community tags on Goodreads/Amazon/BookTok content.

    Searches for "{title} {author} book tropes themes genre" across
    Goodreads, Amazon, and the StoryGraph (which has community discussion
    on other platforms) to extract mood, pace, trope, and warning signals.

    Returns None if no useful content found.
    """
    try:
        results = tavily.search(
            f'"{title}" {author} book tropes themes genre review',
            search_depth="basic",
            include_domains=[
                "goodreads.com",
                "amazon.com",
                "thestorygraph.com",
                "bookofthemonth.com",
                "barnesandnoble.com",
                "romance.io",
            ],
        )
    except Exception as e:
        logger.debug(f"Tavily tag search failed for '{title}': {e}")
        return None

    entries = results.get("results", [])
    if not entries:
        return None

    combined = " ".join(e.get("content", "") for e in entries)

    moods = _extract(combined, MOODS)
    pace = _extract(combined, PACE)
    tropes = _extract(combined, TROPES)
    warnings_list = _extract(combined, set(WARNINGS))

    if tropes:
        logger.info(
            f"Community tags (via Tavily): {len(tropes)} tropes, "
            f"{len(moods)} moods for '{title}'"
        )

    return (
        {
            "moods": moods,
            "pace": pace[0] if pace else None,
            "tropes": tropes,
            "warnings": warnings_list,
        }
        if (moods or tropes)
        else None
    )


def _extract(text: str, vocabulary: set) -> List[str]:
    """Return sorted list of vocabulary items found in text."""
    found = set()
    tl = text.lower()
    for item in vocabulary:
        if item.lower() in tl:
            found.add(item.lower())
    return sorted(found)
