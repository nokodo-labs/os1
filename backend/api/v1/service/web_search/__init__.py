"""web search service - engine search and agentic synthesis."""

from .errors import WebSearchError
from .search import search_web


__all__ = ["WebSearchError", "search_web"]
