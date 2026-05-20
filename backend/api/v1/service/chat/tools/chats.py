"""chat tools - search and read chats."""

from __future__ import annotations

import json

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_summary import ThreadSummary
from api.schemas.search import SearchMode, SearchParams, SearchResultItem
from api.schemas.thread import ThreadListFilters
from api.v1.service import threads as chat_service
from api.v1.service.chat.context import AppContext
from api.v1.service.threads import summaries as chat_summary_service
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


_HYBRID_SEARCH = SearchParams(mode=SearchMode.HYBRID)
_DEFAULT_PAGE_LIMIT = 12
_MAX_PAGE_LIMIT = 20
_MESSAGE_TEXT_LIMIT = 1800
_SUMMARY_TEXT_LIMIT = 3500


class ChatGetInput(BaseModel):
	"""input schema for chat_get tool."""

	model_config = ConfigDict(extra="forbid")

	chat_id: TypeID | None = Field(
		default=None,
		description=(
			"ID of a chat to read. omit chat_id, message_id, and query to list chats."
		),
	)
	message_id: TypeID | None = Field(
		default=None,
		description="ID of a message; returns the chat page containing it.",
	)
	query: str | None = Field(
		default=None,
		description="hybrid search query. omit to get chats instead.",
		min_length=1,
		max_length=500,
	)
	cursor: str | None = Field(
		default=None,
		description="cursor returned by a previous search page.",
	)
	skip: int = Field(
		default=0,
		description=(
			"page offset. for chat pages, skip this many newest messages. "
			"for chat lists, skip this many latest active chats."
		),
		ge=0,
	)
	limit: int = Field(
		default=_DEFAULT_PAGE_LIMIT,
		description="maximum items to return per page. use skip or cursor to continue.",
		ge=1,
		le=_MAX_PAGE_LIMIT,
	)
	include_archived: bool | None = Field(
		default=None,
		description="optionally filter listed chats by archive state.",
	)


def _trim(text: str | None, max_chars: int) -> str | None:
	if text is None or len(text) <= max_chars:
		return text
	return text[:max_chars] + f"\n\n[truncated - showing first {max_chars} chars]"


def _chat_payload(chat: Thread) -> dict[str, object]:
	return {
		"chat_id": str(chat.id),
		"title": chat.title,
		"tags": list(chat.tags or []),
		"is_archived": chat.is_archived,
		"is_temporary": chat.is_temporary,
		"owner_id": str(chat.owner_id),
		"current_message_id": str(chat.current_message_id)
		if chat.current_message_id
		else None,
		"project_ids": [str(project.id) for project in chat.projects],
		"created_at": chat.created_at.isoformat(),
		"updated_at": chat.updated_at.isoformat(),
		"last_activity_at": chat.last_activity_at.isoformat(),
	}


def _message_payload(message: Message) -> dict[str, object]:
	payload: dict[str, object] = {
		"id": str(message.id),
		"chat_id": str(message.thread_id),
		"type": message.type.value,
		"text": _trim(message.text_content, _MESSAGE_TEXT_LIMIT) or "",
		"created_at": message.created_at.isoformat(),
		"updated_at": message.updated_at.isoformat(),
	}
	if message.sender_agent_id:
		payload["sender_agent_id"] = str(message.sender_agent_id)
	if message.sender_user_id:
		payload["sender_user_id"] = str(message.sender_user_id)
	if message.task_id:
		payload["task_id"] = str(message.task_id)
	if message.tool_call_id:
		payload["tool_call_id"] = message.tool_call_id
	if message.is_error is not None:
		payload["is_error"] = message.is_error
	if message.tool_calls:
		payload["tool_calls"] = message.tool_calls
	if message.citations:
		payload["citations"] = message.citations
	return payload


def _summary_payload(summary: ThreadSummary) -> dict[str, object]:
	payload: dict[str, object] = {
		"id": str(summary.id),
		"chat_id": str(summary.thread_id),
		"type": summary.type.value,
		"content": _trim(summary.content, _SUMMARY_TEXT_LIMIT) or "",
		"message_count": summary.message_count,
		"created_at": summary.created_at.isoformat(),
		"updated_at": summary.updated_at.isoformat(),
	}
	if summary.start_message_id:
		payload["start_message_id"] = str(summary.start_message_id)
	if summary.end_message_id:
		payload["end_message_id"] = str(summary.end_message_id)
	return payload


def _search_item_payload(item: SearchResultItem) -> dict[str, object]:
	data = item.model_dump(mode="json")
	if data.get("type") == "thread":
		data["type"] = "chat"
		data["chat_id"] = data.pop("id")
	return data


def _chat_error(exc: HTTPException) -> str:
	return str(exc.detail).replace("Thread", "chat").replace("thread", "chat")


def _message_page(
	messages: list[Message],
	skip: int,
	limit: int,
	target_message_id: TypeID | None = None,
) -> tuple[list[Message], int, bool, bool]:
	total = len(messages)
	page_skip = skip
	if target_message_id is not None:
		matching_index = next(
			(
				index
				for index, message in enumerate(messages)
				if message.id == target_message_id
			),
			None,
		)
		if matching_index is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="message not found in active chat view",
			)
		page_skip = ((total - 1 - matching_index) // limit) * limit
	end = max(total - page_skip, 0)
	start = max(end - limit, 0)
	page = messages[start:end]
	return page, page_skip, start > 0, page_skip > 0


async def _load_message(
	message_id: TypeID,
	app_context: AppContext,
) -> Message:
	return await chat_service.get_message(
		message_id,
		app_context.session,
		principal=app_context.principal,
	)


class ChatGetTool(Tool[AppContext]):
	"""search, list, and read chats."""

	name: str = Field(default="chat_get")
	description: str = Field(
		default=(
			"retrieve chats. provide query to search, chat_id to read a chat page, "
			"message_id to read the chat page containing that message, or omit all "
			"three to list chats in the same order users see them. all search uses "
			"hybrid retrieval."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ChatGetInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = ChatGetInput.model_validate(kwargs)
		try:
			if inp.query and (inp.chat_id or inp.message_id):
				return self.error(
					"provide query, chat_id, or message_id, not combinations",
					__agent_context__,
				)
			if inp.chat_id and inp.message_id:
				return self.error(
					"provide chat_id or message_id, not both",
					__agent_context__,
				)
			if inp.query:
				return await self._search(inp, __agent_context__, __app_context__)
			if inp.chat_id or inp.message_id:
				return await self._chat_page(inp, __agent_context__, __app_context__)
			return await self._list(inp, __agent_context__, __app_context__)
		except HTTPException as exc:
			return self.error(_chat_error(exc), __agent_context__)

	async def _list(
		self,
		inp: ChatGetInput,
		agent_context: AgentContext,
		app_context: AppContext,
	) -> ToolMessage:
		filters = ThreadListFilters(
			is_archived=inp.include_archived,
		)
		chats = await chat_service.list_threads(
			app_context.session,
			principal=app_context.principal,
			filters=filters,
			skip=inp.skip,
			limit=inp.limit,
			sort_by="last_activity_at",
			sort_dir="desc",
		)
		total = await chat_service.count_threads(
			app_context.session,
			principal=app_context.principal,
			filters=filters,
		)
		results: list[dict[str, object]] = []
		for chat in chats:
			results.append(_chat_payload(chat))
		next_skip = inp.skip + len(results) if inp.skip + len(results) < total else None
		out = {
			"status": "success",
			"message": f"found {len(results)} chats",
			"count": len(results),
			"total": total,
			"skip": inp.skip,
			"limit": inp.limit,
			"has_more": inp.skip + len(results) < total,
			"next_skip": next_skip,
			"results": results,
		}
		return self.success(json.dumps(out), agent_context)

	async def _search(
		self,
		inp: ChatGetInput,
		agent_context: AgentContext,
		app_context: AppContext,
	) -> ToolMessage:
		if not inp.query:
			return self.error("query is required when searching chats", agent_context)
		page = await chat_service.search_threads(
			inp.query,
			app_context.session,
			principal=app_context.principal,
			limit=inp.limit,
			cursor=inp.cursor,
			search_params=_HYBRID_SEARCH,
		)
		results = [_search_item_payload(item) for item in page.items]
		out = {
			"status": "success",
			"message": f"found {len(results)} chats",
			"count": len(results),
			"results": results,
			"next_cursor": page.next_cursor,
			"has_more": page.has_more,
		}
		return self.success(json.dumps(out), agent_context)

	async def _chat_page(
		self,
		inp: ChatGetInput,
		agent_context: AgentContext,
		app_context: AppContext,
	) -> ToolMessage:
		target_message_id = inp.message_id
		chat_id = inp.chat_id
		if target_message_id is not None:
			message = await _load_message(target_message_id, app_context)
			chat_id = message.thread_id
		if chat_id is None:
			return self.error("chat_id or message_id is required", agent_context)
		chat = await chat_service.get_thread(
			chat_id,
			app_context.session,
			principal=app_context.principal,
		)
		payload = _chat_payload(chat)
		summaries = await self._summary_payloads(app_context, chat.id)
		if summaries:
			payload["summaries"] = summaries
		messages = await chat_service.get_current_branch(
			chat.id,
			app_context.session,
			principal=app_context.principal,
		)
		message_page, page_skip, has_more_older, has_more_newer = _message_page(
			messages,
			inp.skip,
			inp.limit,
			target_message_id=target_message_id,
		)
		message_results = [_message_payload(message) for message in message_page]
		out = {
			"status": "success",
			"message": "chat page retrieved",
			"chat": payload,
			"message_page": {
				"count": len(message_results),
				"total": len(messages),
				"skip": page_skip,
				"limit": inp.limit,
				"has_more_older": has_more_older,
				"has_more_newer": has_more_newer,
				"next_skip": page_skip + len(message_results)
				if has_more_older
				else None,
				"previous_skip": max(page_skip - inp.limit, 0)
				if has_more_newer
				else None,
				"target_message_id": str(target_message_id)
				if target_message_id
				else None,
				"results": message_results,
			},
		}
		return self.success(json.dumps(out), agent_context)

	async def _summary_payloads(
		self,
		app_context: AppContext,
		chat_id: TypeID,
	) -> list[dict[str, object]]:
		summaries = await chat_summary_service.list_active_summaries(
			chat_id,
			app_context.session,
		)
		return [_summary_payload(summary) for summary in summaries]
