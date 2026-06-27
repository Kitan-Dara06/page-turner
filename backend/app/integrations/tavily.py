from tavily import TavilyClient

from app.config import settings

client = TavilyClient(api_key=settings.TAVILY_API_KEY)


def search(
    query: str,
    search_depth: str = "advanced",
    include_raw_content: bool = False,
    **kwargs,
) -> dict:
    """Raw wrapper around Tavily search. Forwards all kwargs to the SDK."""
    return client.search(
        query=query,
        search_depth=search_depth,
        include_raw_content=include_raw_content,
        **kwargs,
    )


def verify_hallucination(book_title: str, author: str) -> bool:
    """Confirm a book exists by searching for author + title. Returns True if results found."""
    query = f'{author} author "{book_title}" book'
    results = search(
        query,
        search_depth="basic",
        include_domains=["goodreads.com", "amazon.com", "thestorygraph.com"],
    )
    return len(results.get("results", [])) > 0
