"""web search engine adapter layer."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
import perplexity as perplexity_sdk

from api.perplexity import PerplexityClient, PerplexitySearchResult
from api.searxng import SearxngClient, SearxngSearchHit
from api.settings import SearchEngine, SearchRecencyFilter, settings
from api.v1.schemas.web_search import WebSearchResult, WebSearchSource

from .errors import WebSearchError


logger = logging.getLogger(__name__)


async def search_web(
	query: str,
	limit: int | None = None,
	include_images: bool | None = None,
	search_recency_filter: SearchRecencyFilter | None = None,
	search_engine: SearchEngine | None = None,
) -> WebSearchResult:
	"""search the web through the configured search engine.

	search engines return result resources. agentic web search consumes these
	resources and performs the synthesis layer separately.
	"""
	_ = include_images
	engine = search_engine or settings.web_search.search_engines.engine
	if engine == "perplexity":
		return await _search_perplexity(
			query,
			limit=limit,
			search_recency_filter=search_recency_filter,
		)
	if engine == "searxng":
		return await _search_searxng(
			query,
			limit=limit,
			search_recency_filter=search_recency_filter,
		)
	if engine in ("bing", "google"):
		raise WebSearchError(f"{engine} search engine is not yet implemented")
	raise WebSearchError(f"unsupported search engine: {engine}")


async def _search_perplexity(
	query: str,
	limit: int | None,
	search_recency_filter: SearchRecencyFilter | None,
) -> WebSearchResult:
	pplx = settings.integrations.perplexity
	if not pplx.api_key:
		raise WebSearchError("perplexity search engine is not configured")

	client = PerplexityClient(api_key=pplx.api_key)
	try:
		response = await client.search(
			query,
			max_results=limit,
			search_recency_filter=search_recency_filter,
		)
	except perplexity_sdk.APIStatusError as exc:
		logger.error(
			"perplexity search engine API error %s: %s",
			exc.status_code,
			str(exc.message)[:200],
		)
		raise WebSearchError(
			f"perplexity search engine API error: {exc.status_code}"
		) from exc
	except perplexity_sdk.APIConnectionError as exc:
		logger.error("perplexity search engine request failed: %s", exc)
		raise WebSearchError("perplexity search engine request failed") from exc

	return WebSearchResult(
		results=_perplexity_sources(response.results),
		engine="perplexity",
	)


async def _search_searxng(
	query: str,
	limit: int | None,
	search_recency_filter: SearchRecencyFilter | None,
) -> WebSearchResult:
	searxng = settings.integrations.searxng
	client = SearxngClient(
		instance_url=str(searxng.instance_url),
		timeout=float(searxng.timeout_seconds),
	)
	try:
		hits = await client.search(
			query,
			max_results=limit or searxng.max_results,
			categories=["general"],
			time_range=_searxng_time_range(search_recency_filter),
		)
	except httpx.HTTPStatusError as exc:
		logger.error(
			"searxng search engine API error %s: %s",
			exc.response.status_code,
			str(exc.response.text)[:200],
		)
		raise WebSearchError(
			f"searxng search engine API error: {exc.response.status_code}"
		) from exc
	except httpx.RequestError as exc:
		logger.error("searxng search engine request failed: %s", exc)
		raise WebSearchError("searxng search engine request failed") from exc

	return WebSearchResult(
		results=_searxng_sources(hits),
		engine="searxng",
	)


def _perplexity_sources(
	results: list[PerplexitySearchResult],
) -> list[WebSearchSource]:
	blacklist = settings.web_search.blacklisted_domains
	return [
		WebSearchSource(
			title=result.title,
			url=result.url,
			snippet=result.snippet,
			date=result.date,
			last_updated=result.last_updated,
		)
		for result in results
		if not is_blacklisted(result.url, blacklist)
	]


def _searxng_sources(results: list[SearxngSearchHit]) -> list[WebSearchSource]:
	blacklist = settings.web_search.blacklisted_domains
	return [
		WebSearchSource(
			title=result.title,
			url=result.url,
			snippet=result.content,
		)
		for result in results
		if not is_blacklisted(result.url, blacklist)
	]


def _searxng_time_range(
	search_recency_filter: SearchRecencyFilter | None,
) -> str:
	match search_recency_filter:
		case "day" | "week" | "month" | "year":
			return search_recency_filter
		case _:
			return ""


def is_blacklisted(url: str, blacklist: list[str]) -> bool:
	"""check whether a URL host matches a blocked domain."""
	if not blacklist:
		return False
	try:
		host = urlparse(url).hostname or ""
	except ValueError:
		return False
	return any(host == domain or host.endswith(f".{domain}") for domain in blacklist)
