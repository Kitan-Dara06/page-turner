import httpx

BASE_URL = "https://openlibrary.org"
# OpenLibrary requires a descriptive User-Agent
HEADERS = {"User-Agent": "PageTurner/1.0 (your_email@example.com)"}


def lookup_work(title: str, author: str) -> dict | None:
    """Searches for the canonical Work entity."""
    params = {"title": title, "author": author, "limit": 1}
    url = f"{BASE_URL}/search.json"

    with httpx.Client(headers=HEADERS) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        docs = response.json().get("docs", [])
        return docs[0] if docs else None


def fetch_editions(work_key: str) -> list[dict]:
    """Fetches all physical/digital editions attached to a Work."""
    url = f"{BASE_URL}{work_key}/editions.json"

    with httpx.Client(headers=HEADERS) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json().get("entries", [])
