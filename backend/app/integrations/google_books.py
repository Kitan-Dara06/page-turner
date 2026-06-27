import httpx

from app.config import settings

BASE_URL = "https://www.googleapis.com/books/v1/volumes"


def search_by_title_author(title: str, author: str) -> list[dict]:
    """Queries Google Books using specific intitle and inauthor operators."""
    query = f"intitle:{title}+inauthor:{author}"
    params = {"q": query, "key": settings.GOOGLE_BOOKS_API_KEY, "maxResults": 3}

    with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        response = client.get(BASE_URL, params=params)
        response.raise_for_status()
        return response.json().get("items", [])


def fetch_by_isbn(isbn: str) -> dict | None:
    """Fetches a specific edition by ISBN."""
    params = {"q": f"isbn:{isbn}", "key": settings.GOOGLE_BOOKS_API_KEY}

    with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        response = client.get(BASE_URL, params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
        return items[0] if items else None
