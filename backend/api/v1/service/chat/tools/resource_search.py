"""resource search tool."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service import search as search_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


type SearchResourceType = Literal[
	"chat",
	"note",
	"reminder",
	"calendar_event",
	"project",
	"file",
]

_HYBRID_SEARCH = SearchParams(mode=SearchMode.HYBRID)
_TYPE_MAP: dict[str, SearchResultType] = {
	"chat": SearchResultType.THREAD,
	"note": SearchResultType.NOTE,
	"reminder": SearchResultType.REMINDER,
	"calendar_event": SearchResultType.CALENDAR_EVENT,
	"project": SearchResultType.PROJECT,
	"file": SearchResultType.FILE,
}


class ResourceSearchInput(BaseModel):
	"""input schema for resource_search tool."""

	model_config = ConfigDict(extra="forbid")

	query: str = Field(
		...,
		description="hybrid search query to run across accessible resources.",
		min_length=1,
		max_length=500,
	)
	types: list[SearchResourceType] | None = Field(
		default=None,
		description=(
			"optional resource types to search. omit to search chats, notes, "
			"reminders, calendar events, projects, and files."
		),
	)
	limit: int = Field(
		default=10,
		description="maximum total results to return.",
		ge=1,
		le=50,
	)


def _result_payload(item: SearchResultItem) -> dict[str, object]:
	"""serialize one search result for the resource_search tool output."""
	data = item.model_dump(mode="json")
	if data.get("type") == "thread":
		data["type"] = "chat"
		data["chat_id"] = data.pop("id")
	return data


class ResourceSearchTool(Tool[AppContext]):
	"""search across accessible user resources."""

	name: str = Field(default="resource_search")
	description: str = Field(
		default=(
			"search across accessible resources, like find mode. searches chats, "
			"notes, reminders, calendar events, projects, and files using hybrid "
			"retrieval only."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ResourceSearchInput.model_json_schema()
	)

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		inp = ResourceSearchInput.model_validate(kwargs)
		resource_types = [_TYPE_MAP[item] for item in inp.types] if inp.types else None
		results: list[dict[str, object]] = []
		async for item in search_service.search_stream(
			inp.query,
			__app_context__.session,
			principal=__app_context__.principal,
			types=resource_types,
			limit=inp.limit,
			search_params=_HYBRID_SEARCH,
		):
			results.append(_result_payload(item))
		out = {
			"status": "success",
			"message": f"found {len(results)} resources",
			"count": len(results),
			"results": results,
		}
		return self.success(json.dumps(out), __tool_call_context__)
