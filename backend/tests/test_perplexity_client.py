"""unit coverage for the official Perplexity SDK wrapper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import perplexity as perplexity_mod
from api.perplexity import PerplexityClient


@pytest.mark.asyncio
async def test_native_search_uses_search_create_and_returns_resources(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	calls: list[dict[str, object]] = []

	class FakeSearchResource:
		async def create(self, **kwargs: object) -> SimpleNamespace:
			calls.append(kwargs)
			return SimpleNamespace(
				results=[
					SimpleNamespace(
						title="native result",
						url="https://example.com/native",
						snippet="resource snippet",
						date="2025-01-01",
						last_updated="2025-01-02",
					)
				]
			)

	class FakeAsyncPerplexity:
		def __init__(self, api_key: str) -> None:
			self.api_key = api_key
			self.search = FakeSearchResource()

		async def __aenter__(self) -> FakeAsyncPerplexity:
			return self

		async def __aexit__(
			self,
			exc_type: type[BaseException] | None,
			exc: BaseException | None,
			tb: object,
		) -> None:
			return None

	monkeypatch.setattr(perplexity_mod, "AsyncPerplexity", FakeAsyncPerplexity)

	result = await PerplexityClient("pplx-key").search(
		"query",
		max_results=3,
		search_recency_filter="week",
		search_domain_filter=["example.com"],
	)

	assert calls == [
		{
			"query": "query",
			"max_results": 3,
			"search_recency_filter": "week",
			"search_domain_filter": ["example.com"],
		}
	]
	assert result.mode == "web"
	assert result.images == []
	assert result.content == "[1] native result\nresource snippet"
	assert result.results[0].url == "https://example.com/native"


@pytest.mark.asyncio
async def test_agentic_search_uses_chat_completions_and_search_results(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	calls: list[dict[str, object]] = []

	class FakeCompletionsResource:
		async def create(self, **kwargs: object) -> SimpleNamespace:
			calls.append(kwargs)
			return SimpleNamespace(
				choices=[
					SimpleNamespace(message=SimpleNamespace(content="agentic summary"))
				],
				search_results=[
					SimpleNamespace(
						title="searched page",
						url="https://example.com/page",
						snippet="page snippet",
						date=None,
						last_updated="2025-02-01",
					)
				],
				model_extra={
					"images": [
						{
							"image_url": "https://cdn.example.com/image.jpg",
							"title": "image title",
							"source_url": "https://example.com/page",
						}
					]
				},
			)

	class FakeChatResource:
		def __init__(self) -> None:
			self.completions = FakeCompletionsResource()

	class FakeAsyncPerplexity:
		def __init__(self, api_key: str) -> None:
			self.api_key = api_key
			self.chat = FakeChatResource()

		async def __aenter__(self) -> FakeAsyncPerplexity:
			return self

		async def __aexit__(
			self,
			exc_type: type[BaseException] | None,
			exc: BaseException | None,
			tb: object,
		) -> None:
			return None

	monkeypatch.setattr(perplexity_mod, "AsyncPerplexity", FakeAsyncPerplexity)

	result = await PerplexityClient("pplx-key").agentic_search(
		"query",
		model="sonar",
		system_prompt="search well",
		temperature=0.1,
		search_context_usage="high",
		search_recency_filter="day",
		return_images=True,
		max_results=4,
		search_domain_filter=["example.com"],
	)

	assert calls[0]["messages"] == [
		{"role": "system", "content": "search well"},
		{"role": "user", "content": "query"},
	]
	assert calls[0]["stream"] is False
	assert calls[0]["web_search_options"] == {"search_context_size": "high"}
	assert calls[0]["num_search_results"] == 4
	assert result.mode == "agentic"
	assert result.content == "agentic summary"
	assert result.results[0].snippet == "page snippet"
	assert result.images[0].url == "https://cdn.example.com/image.jpg"
