"""perplexity search agent - delegates to the perplexity chat completions API."""

from __future__ import annotations

import logging

import httpx

from api.perplexity import PerplexityClient
from api.schemas.citations import Citation, CitationSource
from api.settings import PerplexityModel, settings

from .models import WebSearchError, WebSearchResult


logger = logging.getLogger(__name__)


async def search_perplexity(
	query: str,
	model_override: PerplexityModel | None = None,
	temperature_override: float | None = None,
	search_context_usage_override: str | None = None,
	search_recency_filter_override: str | None = None,
	return_images_override: bool | None = None,
) -> WebSearchResult:
	"""search using the perplexity chat completions API.

	does not support source limiting.

	args:
		query: natural-language search query.
		model_override: override the default perplexity model (None = use settings).

	returns:
		WebSearchResult with summary and citations.
	"""
	pplx = settings.web_search.perplexity
	if not pplx.api_key:
		raise WebSearchError("perplexity web search is not configured")
	client = PerplexityClient(api_key=pplx.api_key)
	try:
		result = await client.search(
			query,
			model=model_override or pplx.model,
			temperature=temperature_override or pplx.temperature,
			search_context_usage=search_context_usage_override
			or pplx.search_context_usage,
			search_recency_filter=search_recency_filter_override
			or pplx.search_recency_filter,
			return_images=return_images_override or pplx.return_images,
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

	citations = [
		Citation(index=i, source_type=CitationSource.URL, source_id=url)
		for i, url in enumerate(result.citations, 1)
	]
	return WebSearchResult(
		query=query,
		summary=result.content,
		citations=citations,
	)
