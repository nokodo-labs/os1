"""agentic web search chat tool."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.settings import SearchRecencyFilter, settings
from api.v1.schemas.web_search import WebSearchSource
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.message_metadata import CITABLE_SOURCES_KEY
from api.v1.service.web_search.agentic import search_agentic_web
from api.v1.service.web_search.errors import WebSearchError
from api.v1.service.web_search.progress import build_agentic_web_search_progress
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject, JSONValue


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
			"from all search results. "
			"refer to your context for current date and time, and ALWAYS keep "
			"your queries UNBIASED and NEUTRAL for best results."
		),
		min_length=1,
		max_length=500,
	)
	limit: int | None = Field(
		default=None,
		description="maximum number of search results to use. none=no limit.",
		ge=1,
	)
	search_recency_filter: SearchRecencyFilter | None = Field(
		default=None,
		description=(
			"restrict search results to a time window. none uses provider default."
		),
	)
	include_images: bool | None = Field(
		default=None,
		description=(
			"include image results when the provider supports it. none uses "
			"the configured default."
		),
	)


class AgenticWebSearchTool(Tool[AppContext]):
	"""perform an AI-powered agentic web search.

	this is the preferred web search tool for general agent use. it runs a
	dedicated search agent/provider flow that gathers sources, synthesizes a
	concise answer, and returns citations. compared with raw search results,
	it keeps the tool output smaller and usually gives the model cleaner
	evidence to cite.
	"""

	name: str = Field(default="agentic_web_search")
	description: str = Field(
		default=(
			"preferred web search tool. uses a search agent to gather sources, "
			"summarize them, and return concise cited results instead of raw "
			"search payloads."
		),
	)
	parameters: JSONObject = Field(
		default_factory=lambda: AgenticWebSearchInput.model_json_schema(),
	)

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		"""run the configured agentic search path and return synthesized results."""
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		inp = AgenticWebSearchInput.model_validate(kwargs)

		async def emit_progress(message: str, payload: JSONObject) -> None:
			"""emit a rich web-search progress event for the frontend."""
			if not __app_context__.thread_id:
				return
			data: JSONObject = {
				"tool_call_id": __tool_call_context__.tool_call_id,
				"tool_name": self.name,
				"tool": {
					"call_id": __tool_call_context__.tool_call_id,
					"name": self.name,
				},
				"message": message,
				"payload": payload,
			}
			await __app_context__.event_emitter(
				Event(
					scope=EventScope.THREAD,
					scope_id=__app_context__.thread_id,
					type=EventType.TOOL_PROGRESS,
					data=data,
					user_id=__app_context__.user_id,
					thread_id=__app_context__.thread_id,
				)
			)

		await emit_progress(
			"searching the web",
			build_agentic_web_search_progress(
				stage="started",
				message="searching the web",
				query=inp.query,
				agent=settings.web_search.agentic.agent,
			),
		)

		try:
			result = await search_agentic_web(
				inp.query,
				limit=inp.limit,
				include_images=inp.include_images,
				search_recency_filter=inp.search_recency_filter,
				app_context=__app_context__,
				progress_callback=emit_progress,
			)
		except WebSearchError:
			logger.exception("agentic web search failed for query: %s", inp.query)
			return self.error(
				"web search failed. please try again.",
				__tool_call_context__,
			)

		sources: list[JSONValue] = [
			{"url": c.source_id, "title": c.title} for c in result.citations
		]
		images: list[JSONValue] = [
			{"url": img.url, "title": img.title, "source_url": img.source_url}
			for img in result.images
		]
		if result.agent != "native":
			final_message = f"found {len(sources)} resources"
			await emit_progress(
				final_message,
				build_agentic_web_search_progress(
					stage="completed",
					message=final_message,
					query=inp.query,
					agent=result.agent,
					engine=result.engine,
					result_count=len(sources),
					sources=[
						WebSearchSource(
							title=c.title or c.source_id, url=c.source_id, snippet=""
						)
						for c in result.citations
					],
					images=result.images,
				),
			)

		citable_sources: list[JSONValue] = [
			{"source_type": c.source_type, "source_id": c.source_id, "title": c.title}
			for c in result.citations
		]
		max_chars = settings.web_search.max_chars
		summary = result.summary
		if len(summary) > max_chars:
			summary = (
				summary[:max_chars]
				+ f"\n\n[truncated - showing first {max_chars} chars]"
			)
		payload: JSONObject = {
			"summary": summary,
			"images": images,
		}
		metadata: JSONObject = {
			CITABLE_SOURCES_KEY: citable_sources,
			"_web_search": {
				"agent": result.agent,
				"engine": result.engine,
				"source_count": len(citable_sources),
				"image_count": len(images),
			},
		}
		output = json.dumps(payload, ensure_ascii=True)

		return ToolMessage(
			tool_call_id=__tool_call_context__.tool_call_id,
			tool_output=output,
			metadata=metadata,
		)
