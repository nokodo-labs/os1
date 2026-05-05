"""unit coverage for perplexity-backed web search plumbing."""

from __future__ import annotations

import json
from unittest.mock import ANY, AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.models.user import User
from api.perplexity import _parse_images
from api.schemas.citations import Citation, CitationSource
from api.v1.schemas.web_search import (
	AgenticWebSearchResult,
	WebSearchImage,
	WebSearchResult,
	WebSearchSource,
)
from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext, EventEmitter
from api.v1.service.chat.tools import agentic_web_search as tool_mod
from api.v1.service.chat.tools.agentic_web_search import AgenticWebSearchTool
from api.v1.service.chat.tools.web_search import WebSearchTool
from api.v1.service.web_search.search import is_blacklisted
from nokodo_ai import ChatModel
from nokodo_ai.context import AgentContext
from nokodo_ai.threads import Thread
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _agent_context(tool_call_id: str) -> AgentContext:
	return AgentContext(
		thread=Thread(),
		model=ChatModel.model_construct(model_name="stub"),
		tool_call_id=tool_call_id,
	)


async def _noop_event_emitter(event: Event) -> None:
	_ = event


def _app_context(
	event_emitter: EventEmitter = _noop_event_emitter,
	thread_id: TypeID | None = None,
) -> AppContext:
	user = User(
		id=new_typeid("user"),
		email="web-search@example.com",
		username="web_search_user",
		hashed_password="x",
		is_superuser=True,
	)
	return AppContext(
		session=AsyncSession(),
		principal=Principal(user=user, group_ids=(), permissions=frozenset()),
		event_emitter=event_emitter,
		thread_id=thread_id,
	)


def test_blacklist_matches_domain_and_subdomain() -> None:
	blacklist = ["example.com"]

	assert is_blacklisted("https://example.com/news", blacklist)
	assert is_blacklisted("https://www.example.com/news", blacklist)
	assert not is_blacklisted("https://other.example.org/news", blacklist)


def test_parse_images_accepts_urls_and_structured_results() -> None:
	images = _parse_images(
		[
			"https://cdn.example.com/a.jpg",
			{
				"image_url": "https://cdn.example.com/b.webp",
				"title": "result b",
				"source_url": "https://example.com/b",
			},
			{"title": "missing url"},
		]
	)

	assert len(images) == 2
	assert images[0].url == "https://cdn.example.com/a.jpg"
	assert images[1].url == "https://cdn.example.com/b.webp"
	assert images[1].title == "result b"
	assert images[1].source_url == "https://example.com/b"


@pytest.mark.asyncio
async def test_web_search_tool_returns_citable_sources_and_images(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	result = AgenticWebSearchResult(
		summary="agentic summary",
		citations=[
			Citation(
				index=1,
				source_type=CitationSource.URL,
				source_id="https://example.com/news",
				title="example news",
			)
		],
		images=[
			WebSearchImage(
				url="https://cdn.example.com/news.jpg",
				title="news image",
				source_url="https://example.com/news",
			)
		],
		agent="perplexity",
		engine="perplexity",
	)
	tool = AgenticWebSearchTool()
	ctx = _agent_context("tool_1")
	events: list[Event] = []

	async def collect_event(event: Event) -> None:
		events.append(event)

	app_ctx = _app_context(collect_event, new_typeid("thread"))

	try:
		monkeypatch.setattr(tool_mod.settings.web_search.agentic, "agent", "perplexity")
		with patch(
			"api.v1.service.chat.tools.agentic_web_search.search_agentic_web",
			new=AsyncMock(return_value=result),
		) as search_mock:
			message = await tool.call(
				ctx,
				app_ctx,
				query="latest nokodo news",
				limit=3,
				include_images=True,
				search_recency_filter="week",
			)
	finally:
		await app_ctx.session.close()

	search_mock.assert_awaited_once_with(
		"latest nokodo news",
		limit=3,
		include_images=True,
		search_recency_filter="week",
		app_context=app_ctx,
		progress_callback=ANY,
	)
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["summary"] == "agentic summary"
	assert "sources" not in payload
	assert payload["images"] == [
		{
			"url": "https://cdn.example.com/news.jpg",
			"title": "news image",
			"source_url": "https://example.com/news",
		}
	]
	assert message.metadata == {
		"_citable_sources": [
			{
				"source_type": CitationSource.URL,
				"source_id": "https://example.com/news",
				"title": "example news",
			}
		],
		"_web_search": {
			"agent": "perplexity",
			"engine": "perplexity",
			"source_count": 1,
			"image_count": 1,
		},
	}
	assert [event.data["message"] for event in events] == [
		"searching the web",
		"found 1 resources",
	]
	started_payload = events[0].data["payload"]
	assert isinstance(started_payload, dict)
	started_web_search = started_payload["web_search"]
	assert isinstance(started_web_search, dict)
	assert started_web_search["stage"] == "started"
	assert started_web_search["agent"] == {"name": "perplexity"}
	completed_payload = events[-1].data["payload"]
	assert isinstance(completed_payload, dict)
	completed_web_search = completed_payload["web_search"]
	assert isinstance(completed_web_search, dict)
	assert completed_web_search["stage"] == "completed"
	assert completed_web_search["engine"] == {"name": "perplexity"}
	resources = completed_web_search["resources"]
	assert isinstance(resources, dict)
	assert resources["count"] == 1
	assert resources["sources"] == [
		{
			"title": "example news",
			"url": "https://example.com/news",
			"snippet": "",
			"date": None,
			"last_updated": None,
		}
	]


@pytest.mark.asyncio
async def test_standard_search_tool_consumes_configured_search_engine() -> None:
	result = WebSearchResult(
		engine="perplexity",
		results=[
			WebSearchSource(
				title="example news",
				url="https://example.com/news",
				snippet="nokodo news snippet",
			)
		],
	)
	tool = WebSearchTool(default_limit=3)
	ctx = _agent_context("web_search_tool_1")

	with patch(
		"api.v1.service.chat.tools.web_search.search_web",
		new=AsyncMock(return_value=result),
	) as engine_mock:
		message = await tool.call(ctx, None, query="latest nokodo news")

	engine_mock.assert_awaited_once_with(
		"latest nokodo news",
		limit=3,
		include_images=None,
		search_recency_filter=None,
	)
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"] == [
		{
			"title": "example news",
			"url": "https://example.com/news",
			"snippet": "nokodo news snippet",
			"date": None,
			"last_updated": None,
		}
	]
	assert message.metadata == {
		"_citable_sources": [
			{
				"source_type": "url",
				"source_id": "https://example.com/news",
				"title": "example news",
			}
		],
		"_web_search": {
			"engine": "perplexity",
			"result_count": 1,
			"image_count": 0,
		},
	}
