import logging

from app.config import settings

logger = logging.getLogger(__name__)


def fetch_subreddit_posts_by_keyword(subreddit: str, keyword: str, limit: int = 10):
    """
    Reddit API is currently unavailable.
    Returns an empty list and logs a warning.
    """
    logger.warning(
        f"Reddit API unavailable — skipping subreddit search for '{keyword}' in r/{subreddit}"
    )
    return []
