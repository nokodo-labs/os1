"""web search and direct URL content fetching tools."""

from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from api.settings import SearchRecencyFilter, settings
from api.v1.service.chat.context import AppContext
from api.v1.service.web_search.errors import WebSearchError
from api.v1.service.web_search.loaders import fetch_url
from api.v1.service.web_search.progress import source_payload
from api.v1.service.web_search.search import search_web
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject, JSONValue


logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
	"""input schema for web_search tool."""

	model_config = ConfigDict(extra="forbid")

	query: str = Field(
		...,
		description=(
			"search query to send to the configured web search engine. use this "
			"to retrieve source resources before synthesizing an answer."
		),
	)
	limit: int | None = Field(
		default=None,
		ge=1,
		description="maximum number of search results to return. none uses default.",
	)
	search_recency_filter: SearchRecencyFilter | None = Field(
		default=None,
		description="restrict search results to a time window. none uses default.",
	)
	include_images: bool | None = Field(
		default=None,
		description="include image results when the configured engine supports it.",
	)


class WebSearchTool(Tool[AppContext]):
	"""search the web and return source resources."""

	name: str = Field(default="web_search")
	description: str = Field(
		default=(
			"search the web through the configured search engine and return "
			"source result titles, URLs, snippets, and dates."
		),
	)
	parameters: JSONObject = Field(
		default_factory=lambda: WebSearchInput.model_json_schema(),
	)
	default_limit: int | None = Field(default=None, exclude=True)
	default_search_recency_filter: SearchRecencyFilter | None = Field(
		default=None,
		exclude=True,
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		"""run the configured search engine and return structured search results."""
		inp = WebSearchInput.model_validate(kwargs)
		limit = inp.limit if inp.limit is not None else self.default_limit
		search_recency_filter = (
			inp.search_recency_filter
			if inp.search_recency_filter is not None
			else self.default_search_recency_filter
		)

		try:
			result = await search_web(
				inp.query,
				limit=limit,
				include_images=inp.include_images,
				search_recency_filter=search_recency_filter,
			)
		except WebSearchError as exc:
			logger.exception("web search failed for query: %s", inp.query)
			return self.error(str(exc), __agent_context__)

		sources: list[JSONValue] = [
			source_payload(result_source) for result_source in result.results
		]
		images: list[JSONValue] = [
			{"url": image.url, "title": image.title, "source_url": image.source_url}
			for image in result.images
		]
		payload: JSONObject = {
			"results": sources,
			"images": images,
		}
		metadata: JSONObject = {
			"_citable_sources": [
				{
					"source_type": "url",
					"source_id": result_source.url,
					"title": result_source.title,
				}
				for result_source in result.results
			],
			"_web_search": {
				"engine": result.engine,
				"result_count": len(sources),
				"image_count": len(images),
			},
		}
		max_chars = settings.web_search.max_chars
		output = _json_output_with_result_limit(payload, max_chars)
		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=output,
			metadata=metadata,
		)


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
		"""fetch a URL and return structured page content for the model."""
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

		payload: JSONObject = {"title": domain, "content": content}

		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=json.dumps(payload, ensure_ascii=True),
			metadata={
				"_citable_sources": [
					{
						"source_type": "url",
						"source_id": inp.url,
						"title": domain,
					}
				],
				"_web_fetch": {
					"domain": domain,
					"content_chars": len(content),
				},
			},
		)


def _json_output_with_result_limit(payload: JSONObject, max_chars: int) -> str:
	"""serialize search output while preserving valid JSON when trimming results."""
	output = json.dumps(payload, ensure_ascii=True)
	if len(output) <= max_chars:
		return output
	results = payload.get("results")
	if not isinstance(results, list) or len(results) <= 1:
		return output

	limited_results: list[JSONValue] = list(results)
	limited_payload: JSONObject = {
		**payload,
		"results": limited_results,
		"truncated": True,
	}
	while len(limited_results) > 1:
		limited_results = limited_results[:-1]
		limited_payload["results"] = limited_results
		output = json.dumps(limited_payload, ensure_ascii=True)
		if len(output) <= max_chars:
			return output
	return output
