"""unit coverage for web search service adapters."""

from __future__ import annotations

import pytest

from api.perplexity import PerplexitySearchResponse, PerplexitySearchResult
from api.searxng import SearxngSearchHit
from api.v1.service.web_search import search as search_mod
from api.v1.service.web_search.errors import WebSearchError


@pytest.mark.asyncio
async def test_search_web_dispatches_perplexity_and_filters_blacklist(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class FakePerplexityClient:
		def __init__(self, api_key: str) -> None:
			assert api_key == "pplx-key"

		async def search(
			self,
			query: str,
			max_results: int | None,
			search_recency_filter: str | None,
		) -> PerplexitySearchResponse:
			assert query == "query"
			assert max_results == 2
			assert search_recency_filter == "day"
			return PerplexitySearchResponse(
				content="not used",
				results=[
					PerplexitySearchResult(
						title="allowed",
						url="https://example.com/allowed",
						snippet="allowed snippet",
					),
					PerplexitySearchResult(
						title="blocked",
						url="https://blocked.test/page",
						snippet="blocked snippet",
					),
				],
				images=[],
				mode="web",
			)

	monkeypatch.setattr(
		search_mod.settings.integrations.perplexity, "api_key", "pplx-key"
	)
	monkeypatch.setattr(
		search_mod.settings.web_search,
		"blacklisted_domains",
		["blocked.test"],
	)
	monkeypatch.setattr(search_mod, "PerplexityClient", FakePerplexityClient)

	result = await search_mod.search_web(
		"query",
		limit=2,
		search_recency_filter="day",
		search_engine="perplexity",
	)

	assert result.engine == "perplexity"
	assert [source.url for source in result.results] == ["https://example.com/allowed"]


@pytest.mark.asyncio
async def test_search_web_dispatches_searxng_with_time_range(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	calls: list[dict[str, object]] = []

	class FakeSearxngClient:
		def __init__(self, instance_url: str, timeout: float) -> None:
			calls.append({"instance_url": instance_url, "timeout": timeout})

		async def search(
			self,
			query: str,
			max_results: int,
			categories: list[str],
			time_range: str,
		) -> list[SearxngSearchHit]:
			calls.append(
				{
					"query": query,
					"max_results": max_results,
					"categories": categories,
					"time_range": time_range,
				}
			)
			return [
				SearxngSearchHit(
					title="hit",
					url="https://example.com/hit",
					content="hit snippet",
					score=1.0,
				)
			]

	monkeypatch.setattr(search_mod.settings.integrations.searxng, "max_results", 7)
	monkeypatch.setattr(search_mod.settings.integrations.searxng, "timeout_seconds", 12)
	monkeypatch.setattr(search_mod.settings.web_search, "blacklisted_domains", [])
	monkeypatch.setattr(search_mod, "SearxngClient", FakeSearxngClient)

	result = await search_mod.search_web(
		"query",
		limit=None,
		search_recency_filter="year",
		search_engine="searxng",
	)

	assert calls[0]["timeout"] == 12.0
	assert calls[1] == {
		"query": "query",
		"max_results": 7,
		"categories": ["general"],
		"time_range": "year",
	}
	assert result.results[0].snippet == "hit snippet"


@pytest.mark.asyncio
async def test_search_web_rejects_unimplemented_engines() -> None:
	with pytest.raises(
		WebSearchError, match="google search engine is not yet implemented"
	):
		await search_mod.search_web("query", search_engine="google")


def test_searxng_time_range_maps_supported_recency_filters() -> None:
	assert search_mod._searxng_time_range("day") == "day"
	assert search_mod._searxng_time_range("week") == "week"
	assert search_mod._searxng_time_range("month") == "month"
	assert search_mod._searxng_time_range("year") == "year"
	assert search_mod._searxng_time_range("hour") == ""
	assert search_mod._searxng_time_range(None) == ""


def test_search_imports_do_not_require_lazy_imports() -> None:
	import importlib

	agentic_mod = importlib.import_module("api.v1.service.web_search.agentic")
	tool_mod = importlib.import_module("api.v1.service.chat.tools.agentic_web_search")
	registry_mod = importlib.import_module("api.v1.service.chat.tools.registry")

	assert hasattr(agentic_mod, "search_agentic_web")
	assert hasattr(tool_mod, "AgenticWebSearchTool")
	assert "web_search" in registry_mod.TOOL_REGISTRY
	assert "agentic_web_search" in registry_mod.TOOL_REGISTRY
