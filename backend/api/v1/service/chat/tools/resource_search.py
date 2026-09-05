"""resource search tool."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.message import CitationSource
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResourceReferenceType,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service.chat.citation_sources import (
	CitableSource,
	citation_source,
	with_citable_sources,
)
from api.v1.service.chat.context import AppContext
from api.v1.service.search.aggregator import search_stream
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
	"reminder": SearchResultType.REMINDER_LIST,
	"calendar_event": SearchResultType.CALENDAR,
	"project": SearchResultType.PROJECT,
	"file": SearchResultType.FILE,
}
_CITATION_TYPE_MAP: dict[SearchResultType, CitationSource] = {
	SearchResultType.THREAD: CitationSource.THREAD,
	SearchResultType.NOTE: CitationSource.NOTE,
	SearchResultType.REMINDER_LIST: CitationSource.REMINDER_LIST,
	SearchResultType.CALENDAR: CitationSource.CALENDAR,
	SearchResultType.PROJECT: CitationSource.PROJECT,
	SearchResultType.FILE: CitationSource.FILE,
}
_ANCHOR_CITATION_TYPE_MAP: dict[SearchResourceReferenceType, CitationSource] = {
	SearchResourceReferenceType.REMINDER: CitationSource.REMINDER,
	SearchResourceReferenceType.CALENDAR_EVENT: CitationSource.CALENDAR_EVENT,
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
	"""project one global search hit into agent-facing domain data."""
	if item.type is SearchResultType.THREAD:
		if item.anchor is not None:
			return {
				"type": "message",
				"message_id": str(item.anchor.id),
				"chat_id": str(item.id),
				"chat_title": item.title,
				**({"excerpt": item.preview} if item.preview else {}),
			}
		return {
			"type": "chat",
			"chat_id": str(item.id),
			"title": item.title,
			**({"preview": item.preview} if item.preview else {}),
		}
	if item.type is SearchResultType.REMINDER_LIST:
		if item.anchor is not None:
			reminder_payload: dict[str, object] = {
				"type": "reminder",
				"id": str(item.anchor.id),
				"title": item.title,
				"list_id": str(item.id),
			}
			for key in ("status", "due_at", "remind_at", "parent_id"):
				value = item.metadata.get(key)
				if value is not None:
					reminder_payload[key] = value
			return reminder_payload
		return {
			"type": "reminder_list",
			"id": str(item.id),
			"name": item.title,
			**({"description": item.preview} if item.preview else {}),
		}
	if item.type is SearchResultType.CALENDAR:
		if item.anchor is not None:
			event_payload: dict[str, object] = {
				"type": "calendar_event",
				"id": str(item.anchor.id),
				"title": item.title,
				"calendar_id": str(item.id),
			}
			for key in ("start_at", "end_at", "is_recurring"):
				value = item.metadata.get(key)
				if value is not None:
					event_payload[key] = value
			return event_payload
		return {
			"type": "calendar",
			"id": str(item.id),
			"name": item.title,
			**({"description": item.preview} if item.preview else {}),
		}
	data = item.model_dump(
		mode="json",
		include={"type", "id", "title", "preview", "metadata"},
	)
	if not item.metadata:
		data.pop("metadata", None)
	return data


def _result_citation_source(item: SearchResultItem) -> CitableSource:
	"""build the citation source represented by one global search hit."""
	if item.anchor is not None:
		source_type = _ANCHOR_CITATION_TYPE_MAP.get(item.anchor.type)
		if source_type is not None:
			return citation_source(source_type, item.anchor.id, item.title)
	return citation_source(_CITATION_TYPE_MAP[item.type], item.id, item.title)


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
		items: list[SearchResultItem] = []
		async for item in search_stream(
			inp.query,
			__app_context__.session,
			principal=__app_context__.principal,
			types=resource_types,
			limit=inp.limit,
			search_params=_HYBRID_SEARCH,
		):
			items.append(item)
			results.append(_result_payload(item))
		out: dict[str, object] = {
			"status": "success",
			"message": f"found {len(results)} resources",
			"count": len(results),
			"results": results,
		}
		return self.success(
			json.dumps(out),
			__tool_call_context__,
			metadata=with_citable_sources(
				None,
				[_result_citation_source(item) for item in items],
			),
		)
