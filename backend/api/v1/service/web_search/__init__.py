"""web search service - dispatches to the configured search agent."""

from .models import WebSearchError, WebSearchResult
from .search import search_web


__all__ = [
	"WebSearchError",
	"WebSearchResult",
	"search_web",
]
