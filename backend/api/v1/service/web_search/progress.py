"""web search progress event payload helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from api.v1.schemas.web_search import WebSearchImage, WebSearchSource
from nokodo_ai.types.json import JSONObject, JSONValue


type AgenticWebSearchStage = Literal[
	"started",
	"search_started",
	"search_results",
	"reading_results",
	"completed",
]


def source_payload(source: WebSearchSource) -> JSONObject:
	"""serialize a web search source for tool output and events."""
	return {
		"title": source.title,
		"url": source.url,
		"snippet": source.snippet,
		"date": source.date,
		"last_updated": source.last_updated,
	}


def image_payload(image: WebSearchImage) -> JSONObject:
	"""serialize a web search image for tool output and events."""
	return {
		"url": image.url,
		"title": image.title,
		"source_url": image.source_url,
	}


def build_agentic_web_search_progress(
	stage: AgenticWebSearchStage,
	message: str,
	query: str,
	agent: str,
	engine: str | None = None,
	search_query: str | None = None,
	inner_tool_call_id: str | None = None,
	result_count: int | None = None,
	sources: Sequence[WebSearchSource] = (),
	images: Sequence[WebSearchImage] = (),
) -> JSONObject:
	"""build a shared rich event payload for agentic web search progress."""
	source_items: list[JSONValue] = [source_payload(source) for source in sources]
	image_items: list[JSONValue] = [image_payload(image) for image in images]
	query_text = search_query or query
	search: JSONObject = {
		"query": {"text": query_text},
		"status": _search_status(stage),
	}
	if inner_tool_call_id is not None:
		search["id"] = inner_tool_call_id
	if result_count is not None:
		search["result_count"] = result_count
	if source_items:
		search["sources"] = source_items

	web_search: JSONObject = {
		"kind": "agentic_web_search",
		"stage": stage,
		"message": message,
		"agent": {"name": agent},
		"query": {"text": query},
		"searches": [search],
	}
	if engine is not None:
		web_search["engine"] = {"name": engine}
	if source_items or image_items or result_count is not None:
		web_search["resources"] = {
			"count": len(source_items) if source_items else (result_count or 0),
			"sources": source_items,
			"images": image_items,
		}

	payload: JSONObject = {
		"web_search": web_search,
		"queries": [query_text],
		"agent": agent,
		"message": message,
	}
	if engine is not None:
		payload["engine"] = engine
	if source_items:
		payload["sources"] = source_items
	if image_items:
		payload["images"] = image_items
	if result_count is not None:
		payload["result_count"] = result_count
	return payload


def _search_status(stage: AgenticWebSearchStage) -> str:
	"""map an agentic search stage to the frontend search status."""
	match stage:
		case "started" | "search_started":
			return "running"
		case "search_results" | "reading_results":
			return "reading"
		case "completed":
			return "completed"
		case _:
			return "running"
