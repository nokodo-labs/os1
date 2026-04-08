"""native agentic search agent - stub implementation."""

from __future__ import annotations

from nokodo_ai.utils.typeid import TypeID

from .models import WebSearchError, WebSearchResult


async def search_agentic(
	query: str,
	*,
	limit: int | None = None,
	agent_id_override: TypeID | None = None,
) -> WebSearchResult:
	"""perform a native agentic web search.

	TODO: implement native search pipeline (searxng + reranking + synthesis).

	args:
		query: natural-language search query.
		limit: maximum number of sources to include.
		agent_id_override: override the default agent ID (None = use settings).

	raises:
		WebSearchError: always, until implemented.
	"""
	raise WebSearchError("native agentic search is not yet implemented")
