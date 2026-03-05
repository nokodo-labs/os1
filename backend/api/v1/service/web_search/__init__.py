"""web search service - dispatches to configured search agent.

reads settings.web_search to choose the active search agent (perplexity
or native) and delegates to the appropriate api client. translates
raw client responses into domain-level WebSearchResult objects.

usage:
    from api.v1.service.web_search import search_web
    result = await search_web("latest python release notes")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from api.perplexity import PerplexityClient
from api.settings import PerplexityModel, SearchAgent, settings


logger = logging.getLogger(__name__)


class WebSearchError(Exception):
	"""raised when a web search operation fails."""


@dataclass(frozen=True, slots=True)
class Citation:
	"""a cited web source in a search result."""

	url: str
	title: str | None = None


@dataclass(frozen=True, slots=True)
class WebSearchResult:
	"""synthesized result of a web search operation."""

	query: str
	summary: str
	citations: list[Citation] = field(default_factory=list)


async def search_web(
	query: str,
	*,
	limit: int = 5,
	search_agent: SearchAgent | None = None,
	model: PerplexityModel | None = None,
) -> WebSearchResult:
	"""perform an agentic web search using the configured provider.

	dispatches to the active search agent from settings.web_search.

	args:
		query: natural-language search query.
		limit: maximum number of citations to include.
		search_agent: override the default search agent (None = use settings).
		model: override the default perplexity model (None = use settings).

	returns:
		WebSearchResult with summary and citations.

	raises:
		WebSearchError: if the search fails or the provider is misconfigured.
	"""
	ws = settings.web_search
	agent = search_agent or ws.search_agent
	if agent == "perplexity":
		return await _search_perplexity(query, limit=limit, model_override=model)
	# native agent - future task
	raise WebSearchError("native web search agent is not yet implemented")


async def _search_perplexity(
	query: str,
	*,
	limit: int,
	model_override: PerplexityModel | None = None,
) -> WebSearchResult:
	"""search using the perplexity chat completions API."""
	pplx = settings.web_search.perplexity
	if not pplx.api_key:
		raise WebSearchError("perplexity web search is not configured")
	client = PerplexityClient(api_key=pplx.api_key)
	try:
		result = await client.search(
			query,
			model=model_override or pplx.model,
			temperature=pplx.temperature,
			search_context_usage=pplx.search_context_usage,
			search_recency_filter=pplx.search_recency_filter,
			return_images=pplx.return_images,
		)
	except httpx.HTTPStatusError as exc:
		logger.error(
			"perplexity API error %s: %s",
			exc.response.status_code,
			exc.response.text[:200],
		)
		raise WebSearchError(
			f"perplexity API error: {exc.response.status_code}"
		) from exc
	except httpx.RequestError as exc:
		logger.error("perplexity request failed: %s", exc)
		raise WebSearchError("perplexity request failed") from exc

	citations = [Citation(url=url) for url in result.citations[:limit]]
	return WebSearchResult(
		query=query,
		summary=result.content,
		citations=citations,
	)


__all__ = [
	"Citation",
	"WebSearchError",
	"WebSearchResult",
	"search_web",
]
