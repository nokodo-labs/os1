"""unit coverage for agentic web search service behavior."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.models.user import User
from api.perplexity import (
	PerplexityImageResult,
	PerplexitySearchResponse,
	PerplexitySearchResult,
)
from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.tools.web_search import WebSearchTool
from api.v1.service.web_search import agentic as agentic_mod
from api.v1.service.web_search.agentic import NativeAgenticWebSearchConfig
from api.v1.service.web_search.errors import WebSearchError
from nokodo_ai import ChatModel
from nokodo_ai.deltas import AgentDelta, ChatModelDelta
from nokodo_ai.messages import AssistantMessage, ToolCall, ToolMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import new_typeid


async def _noop_event_emitter(event: Event) -> None:
	_ = event


def _app_context() -> AppContext:
	user = User(
		id=new_typeid("user"),
		email="agentic-web-search@example.com",
		username="agentic_web_search_user",
		hashed_password="x",
		is_superuser=True,
	)
	return AppContext(
		session=AsyncSession(),
		principal=Principal(user=user, group_ids=(), permissions=frozenset()),
		event_emitter=_noop_event_emitter,
	)


@pytest.mark.asyncio
async def test_agentic_perplexity_filters_sources_and_images(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class FakePerplexityClient:
		def __init__(self, api_key: str) -> None:
			assert api_key == "pplx-key"

		async def agentic_search(
			self,
			query: str,
			**kwargs: object,
		) -> PerplexitySearchResponse:
			assert query == "query"
			assert kwargs["return_images"] is True
			assert kwargs["max_results"] == 4
			return PerplexitySearchResponse(
				content="agentic summary",
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
				images=[
					PerplexityImageResult(
						url="https://cdn.example.com/img.jpg",
						title="image",
						source_url="https://example.com/allowed",
					),
					PerplexityImageResult(
						url="https://blocked.test/img.jpg",
						title="blocked image",
					),
				],
				mode="agentic",
			)

	monkeypatch.setattr(
		agentic_mod.settings.integrations.perplexity,
		"api_key",
		"pplx-key",
	)
	monkeypatch.setattr(
		agentic_mod.settings.integrations.perplexity,
		"image_results_enabled",
		True,
	)
	monkeypatch.setattr(
		agentic_mod.settings.web_search,
		"blacklisted_domains",
		["blocked.test"],
	)
	monkeypatch.setattr(agentic_mod, "PerplexityClient", FakePerplexityClient)

	result = await agentic_mod._search_perplexity_agent(
		"query",
		limit=4,
		include_images=True,
		search_recency_filter="week",
	)

	assert result.summary == "agentic summary"
	assert [citation.source_id for citation in result.citations] == [
		"https://example.com/allowed"
	]
	assert [image.url for image in result.images] == ["https://cdn.example.com/img.jpg"]


@pytest.mark.asyncio
async def test_agentic_perplexity_image_results_must_be_enabled(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class FakePerplexityClient:
		def __init__(self, api_key: str) -> None:
			assert api_key == "pplx-key"

		async def agentic_search(
			self,
			query: str,
			**kwargs: object,
		) -> PerplexitySearchResponse:
			assert query == "query"
			assert kwargs["return_images"] is False
			return PerplexitySearchResponse(
				content="agentic summary",
				results=[],
				images=[],
				mode="agentic",
			)

	monkeypatch.setattr(
		agentic_mod.settings.integrations.perplexity,
		"api_key",
		"pplx-key",
	)
	monkeypatch.setattr(
		agentic_mod.settings.integrations.perplexity,
		"image_results_enabled",
		False,
	)
	monkeypatch.setattr(agentic_mod, "PerplexityClient", FakePerplexityClient)

	result = await agentic_mod._search_perplexity_agent(
		"query",
		limit=4,
		include_images=True,
		search_recency_filter=None,
	)

	assert result.images == []


@pytest.mark.asyncio
async def test_native_agentic_search_rejects_missing_context_and_images() -> None:
	with pytest.raises(WebSearchError, match="images are not supported"):
		await agentic_mod.search_agentic_web(
			"query",
			include_images=True,
			search_agent="native",
		)

	with pytest.raises(WebSearchError, match="app context is required"):
		await agentic_mod.search_agentic_web("query", search_agent="native")


@pytest.mark.asyncio
async def test_native_agent_uses_sdk_run_and_collects_tool_sources(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	captured: dict[str, object] = {}

	class FakeSDKAgent:
		@classmethod
		def __class_getitem__(cls, item: object) -> type[FakeSDKAgent]:
			_ = item
			return cls

		def __init__(
			self,
			chat_model: ChatModel,
			tools: list[object],
			max_iterations: int,
		) -> None:
			captured["chat_model"] = chat_model
			captured["tools"] = tools
			captured["max_iterations"] = max_iterations

		async def run(
			self,
			thread: object,
			app_context: AppContext | None,
			tool_choice: str,
			stream: bool,
		) -> object:
			captured["thread"] = thread
			captured["app_context"] = app_context
			captured["tool_choice"] = tool_choice
			captured["stream"] = stream

			async def stream_deltas() -> AsyncIterator[AgentDelta]:
				yield AgentDelta(
					chat=ChatModelDelta(
						message=AssistantMessage(
							tool_calls=[
								ToolCall(
									id="tool-1",
									name="web_search",
									arguments='{"query": "query"}',
								)
							]
						)
					)
				)
				yield AgentDelta(chat=ChatModelDelta.done_sentinel(chunk_index=1))
				yield AgentDelta(
					tool=ToolMessage(
						tool_call_id="tool-1",
						tool_output=(
							'{"results":['
							'{"title":"source","url":"https://example.com/source",'
							'"snippet":"snippet"},'
							'{"title":"source duplicate",'
							'"url":"https://example.com/source",'
							'"snippet":"duplicate"}]}'
						),
						metadata={"_web_search": {"engine": "perplexity"}},
					)
				)
				yield AgentDelta(
					chat=ChatModelDelta(
						message=AssistantMessage.from_text("native summary")
					)
				)
				yield AgentDelta(chat=ChatModelDelta.done_sentinel(chunk_index=2))
				yield AgentDelta.done_sentinel(chunk_index=5)

			return stream_deltas()

	app_context = _app_context()
	chat_model = ChatModel.model_construct(model_name="stub")
	progress_events: list[tuple[str, JSONObject]] = []

	async def record_progress(message: str, payload: JSONObject) -> None:
		progress_events.append((message, payload))

	config = NativeAgenticWebSearchConfig(
		chat_model=chat_model,
		system_prompt="search system",
		max_iterations=6,
	)

	try:
		monkeypatch.setattr(agentic_mod, "SDKAgent", FakeSDKAgent)
		monkeypatch.setattr(
			agentic_mod,
			"_resolve_native_agentic_config",
			AsyncMock(return_value=config),
		)

		result = await agentic_mod._search_native_agent(
			"query",
			limit=5,
			agent_id_override=None,
			search_recency_filter="week",
			app_context=app_context,
			progress_callback=record_progress,
		)
	finally:
		await app_context.session.close()

	assert captured["max_iterations"] == 6
	assert captured["tool_choice"] == "auto"
	assert captured["stream"] is True
	tools = captured["tools"]
	assert isinstance(tools, list)
	assert len(tools) == 1
	assert isinstance(tools[0], WebSearchTool)
	assert tools[0].default_limit == 5
	assert tools[0].default_search_recency_filter == "week"
	assert result.summary == "native summary"
	assert result.engine == "perplexity"
	assert [citation.source_id for citation in result.citations] == [
		"https://example.com/source"
	]
	assert [message for message, _payload in progress_events] == [
		'searched "query"',
		'"query" found 2 results',
		"reading 2 results",
		"found 1 resources",
	]
	first_payload = progress_events[0][1]["web_search"]
	assert isinstance(first_payload, dict)
	assert first_payload["stage"] == "search_started"
	assert first_payload["agent"] == {"name": "native"}
	first_searches = first_payload["searches"]
	assert isinstance(first_searches, list)
	assert first_searches[0] == {
		"query": {"text": "query"},
		"status": "running",
		"id": "tool-1",
	}
	result_payload = progress_events[1][1]["web_search"]
	assert isinstance(result_payload, dict)
	assert result_payload["stage"] == "search_results"
	resources = result_payload["resources"]
	assert isinstance(resources, dict)
	assert resources["count"] == 2
	assert resources["sources"] == [
		{
			"title": "source",
			"url": "https://example.com/source",
			"snippet": "snippet",
			"date": None,
			"last_updated": None,
		},
		{
			"title": "source duplicate",
			"url": "https://example.com/source",
			"snippet": "duplicate",
			"date": None,
			"last_updated": None,
		},
	]
	final_payload = progress_events[-1][1]["web_search"]
	assert isinstance(final_payload, dict)
	assert final_payload["stage"] == "completed"
	final_resources = final_payload["resources"]
	assert isinstance(final_resources, dict)
	assert final_resources["count"] == 1


def test_collect_web_search_sources_ignores_invalid_and_deduplicates() -> None:
	messages = [
		ToolMessage(
			tool_call_id="tool-1",
			tool_output=(
				'{"results":['
				'{"title":"one","url":"https://example.com/one",'
				'"snippet":"snippet one"},'
				'{"title":"duplicate","url":"https://example.com/one",'
				'"snippet":"duplicate"},'
				'{"url":"https://example.com/missing-title"},'
				'"not an object"]}'
			),
		),
		AssistantMessage.from_text("final answer"),
	]

	sources = agentic_mod._collect_web_search_sources(messages)

	assert [source.url for source in sources] == ["https://example.com/one"]
	assert agentic_mod._last_assistant_text(messages) == "final answer"
