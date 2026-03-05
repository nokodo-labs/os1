"""web search tools - agentic search and direct URL content fetching."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from api.settings import SearchAgent
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

	query: str = Field(
		...,
		description=(
			"the search query. be specific and self-contained - include all "
			"context needed to find the answer without additional conversation "
			"history."
		),
	)
	limit: int = Field(
		default=5,
		description="maximum number of source citations to include in the result",
		ge=1,
		le=10,
	)
	search_agent: SearchAgent | None = Field(
		default=None,
		description=(
			"which AI search agent to use. None = use the app default from settings."
		),
	)


class AgenticWebSearchTool(Tool[AppContext]):
	"""perform an AI-powered agentic web search.

	returns a synthesized answer with source citations.
	"""

	name: str = Field(default="agentic_web_search")
	description: str = Field(
		default=(
			"perform an AI-powered web search using an agentic search engine. "
			"returns a synthesized summary with source citations. use when the "
			"user asks about current events, real-time data, or anything beyond "
			"your training cutoff."
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
		try:
			result = await search_web(
				inp.query, limit=inp.limit, search_agent=inp.search_agent
			)
		except WebSearchError as exc:
			return self.error(str(exc), __agent_context__)

		parts = [result.summary]
		if result.citations:
			parts.append("\nsources:")
			for i, c in enumerate(result.citations, 1):
				label = c.title or c.url
				parts.append(f"{i}. {label} - {c.url}")
		return self.success("\n".join(parts), __agent_context__)


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
		except WebSearchError as exc:
			return self.error(str(exc), __agent_context__)
		except httpx.HTTPStatusError as exc:
			return self.error(
				f"HTTP {exc.response.status_code} fetching {inp.url}",
				__agent_context__,
			)
		except httpx.RequestError as exc:
			return self.error(
				f"request failed for {inp.url}: {exc}",
				__agent_context__,
			)

		domain = parsed.netloc or "unknown"
		# truncate very large pages to avoid token overflow
		max_chars = 50_000
		if len(content) > max_chars:
			content = (
				content[:max_chars]
				+ f"\n\n[truncated - showing first {max_chars} chars]"
			)

		return self.success(f"content from {domain}:\n\n{content}", __agent_context__)
