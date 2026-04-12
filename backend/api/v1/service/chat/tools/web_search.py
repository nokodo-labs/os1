"""web search tools - agentic search and direct URL content fetching."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.settings import settings
from api.v1.service.chat.context import AppContext
from api.v1.service.web_search import WebSearchError, search_web
from api.v1.service.web_search.loaders import fetch_url
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class AgenticWebSearchInput(BaseModel):
	"""input schema for agentic_web_search tool."""

	model_config = ConfigDict(extra="forbid")

	query: str = Field(
		...,
		description=(
			"the search query sent to an AI search agent. unlike a simple "
			"search engine, you can ask compound, multi-part, "
			"or nuanced questions and will get a synthesized answer "
			"from all search results."
			"refer to your context for curent date and time, and ALWAYS keep "
			"your queries UNBIASED and NEUTRAL for best results."
		),
	)
	limit: int | None = Field(
		default=None,
		description="maximum number of search results to use. none=no limit.",
		ge=1,
	)


class AgenticWebSearchTool(Tool[AppContext]):
	"""perform an AI-powered agentic web search.

	returns a synthesized answer with source citations.
	"""

	name: str = Field(default="agentic_web_search")
	description: str = Field(
		default=(
			"perform an AI-powered web search using an AI agent. "
			"returns a summary with source citations. use when the "
			"user asks about current events, real-time data, or anything you "
			"can't confidently answer with your knowledge alone."
		),
	)
	parameters: JSONObject = Field(
		default_factory=lambda: AgenticWebSearchInput.model_json_schema(),
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = AgenticWebSearchInput.model_validate(kwargs)

		# emit searching event with query
		if __app_context__.thread_id:
			await __app_context__.event_emitter(
				Event(
					scope=EventScope.THREAD,
					scope_id=__app_context__.thread_id,
					type=EventType.TOOL_PROGRESS,
					data={
						"tool_call_id": __agent_context__.tool_call_id,
						"tool_name": self.name,
						"message": "searching the web",
						"payload": {"queries": [inp.query]},
					},
					user_id=__app_context__.user_id,
					thread_id=__app_context__.thread_id,
				)
			)

		try:
			result = await search_web(inp.query, limit=inp.limit)
		except WebSearchError:
			logger.exception("agentic web search failed for query: %s", inp.query)
			return self.error(
				"web search failed. please try again.",
				__agent_context__,
			)

		# emit results event with sources
		sources = [{"url": c.source_id, "title": c.title} for c in result.citations]
		if __app_context__.thread_id:
			await __app_context__.event_emitter(
				Event(
					scope=EventScope.THREAD,
					scope_id=__app_context__.thread_id,
					type=EventType.TOOL_PROGRESS,
					data={
						"tool_call_id": __agent_context__.tool_call_id,
						"tool_name": self.name,
						"message": f"found {len(sources)} sources",
						"payload": {"sources": sources},
					},
					user_id=__app_context__.user_id,
					thread_id=__app_context__.thread_id,
				)
			)

		parts = [result.summary]
		if result.citations:
			parts.append("\nsources:")
			for i, c in enumerate(result.citations, 1):
				label = c.title or c.source_id
				parts.append(f"{i}. {label} - {c.source_id}")

		output = "\n".join(parts)
		max_chars = settings.web_search.max_chars
		if len(output) > max_chars:
			output = (
				output[:max_chars]
				+ f"\n\n[truncated - showing first {max_chars} chars]"
			)

		return self.success(output, __agent_context__)


# - fetch URL tool


class FetchUrlInput(BaseModel):
	"""input schema for fetch_url tool."""

	url: str = Field(
		...,
		description=(
			"the URL to fetch content from. supports webpages, articles, "
			"and other online resources."
		),
	)


class FetchUrlTool(Tool[AppContext]):
	"""fetch and return content from a URL."""

	name: str = Field(default="fetch_url")
	description: str = Field(
		default=(
			"browse and retrieve the full content from a URL including "
			"webpages, articles, and other online resources. use this when "
			"you need to read the content of a specific link or URL."
		),
	)
	parameters: JSONObject = Field(
		default_factory=lambda: FetchUrlInput.model_json_schema(),
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = FetchUrlInput.model_validate(kwargs)

		parsed = urlparse(inp.url)
		if parsed.scheme not in ("http", "https"):
			return self.error(
				f"unsupported URL scheme: {parsed.scheme or 'none'}",
				__agent_context__,
			)

		try:
			content = await fetch_url(inp.url)
		except WebSearchError:
			logger.exception("fetch_url web search error for %s", inp.url)
			return self.error(
				f"failed to fetch {inp.url}",
				__agent_context__,
			)
		except httpx.HTTPStatusError as exc:
			return self.error(
				f"HTTP {exc.response.status_code} fetching {inp.url}",
				__agent_context__,
			)
		except httpx.RequestError:
			logger.exception("fetch_url request error for %s", inp.url)
			return self.error(
				f"failed to fetch {inp.url}",
				__agent_context__,
			)

		domain = parsed.netloc or "unknown"
		max_chars = settings.web_search.web_loaders.max_chars
		if len(content) > max_chars:
			content = (
				content[:max_chars]
				+ f"\n\n[truncated - showing first {max_chars} chars]"
			)

		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=f"content from {domain}:\n\n{content}",
			metadata={
				"citable_sources": [
					{"source_type": "url", "source_id": inp.url, "title": domain},
				],
			},
		)
