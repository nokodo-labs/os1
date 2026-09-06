"""chat tools - search and read chats."""

import json

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.schemas.message import CitationSource
from api.schemas.search import SearchMode, SearchParams
from api.schemas.thread import ThreadListFilters
from api.v1.service.chat.citation_sources import citation_source, with_citable_sources
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.tools.base import Tool
from api.v1.service.search.primitives import SearchHit
from api.v1.service.threads import (
	count_threads,
	get_branch_page,
	get_message,
	get_thread,
	list_threads,
	search_threads,
)
from api.v1.service.threads.summaries import (
	latest_active_summary_text,
	list_active_summaries,
)
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
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
		description="ID of a message to locate and read in its chat.",
	)
	before: int | None = Field(
		default=None,
		description="with message_id, number of earlier messages to include.",
		ge=0,
		le=_MAX_PAGE_LIMIT - 1,
	)
	after: int | None = Field(
		default=None,
		description="with message_id, number of later messages to include.",
		ge=0,
		le=_MAX_PAGE_LIMIT - 1,
	)
	query: str | None = Field(
		default=None,
		description="hybrid search query. omit to get chats instead.",
		min_length=1,
		max_length=500,
	)
	offset: int = Field(
		default=0,
		description="number of search results to skip before this page.",
		ge=0,
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
		description="maximum items to return per page. use skip or offset to continue.",
		ge=1,
		le=_MAX_PAGE_LIMIT,
	)
	include_archived: bool | None = Field(
		default=None,
		description="optionally filter listed chats by archive state.",
	)

	@model_validator(mode="after")
	def _validate_message_window(self) -> ChatGetInput:
		if (
			self.before is not None or self.after is not None
		) and self.message_id is None:
			raise ValueError("before and after require message_id")
		if (self.before or 0) + (self.after or 0) + 1 > _MAX_PAGE_LIMIT:
			raise ValueError(
				f"message windows may contain at most {_MAX_PAGE_LIMIT} messages"
			)
		return self


def _trim(text: str | None, max_chars: int) -> str | None:
	if text is None or len(text) <= max_chars:
		return text
	return text[:max_chars] + f"\n\n[truncated - showing first {max_chars} chars]"


def _chat_payload(chat: Thread) -> dict[str, object]:
	return {
		"chat_id": str(chat.id),
		"title": chat.title,
		"tags": list(chat.tags or []),
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
		"purpose": summary.purpose.value,
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


def _thread_search_result(
	thread: Thread,
	hit: SearchHit,
) -> dict[str, object]:
	"""project a chat search hit into agent-facing domain data."""
	summary = latest_active_summary_text(thread, SummaryPurpose.CATALOG)
	if summary is None:
		summary = thread.public_metadata.get("summary")
	if hit.anchor is not None:
		message_payload: dict[str, object] = {
			"type": "message",
			"message_id": str(hit.anchor.id),
			"chat_id": str(thread.id),
			"chat_title": thread.title or "",
		}
		if hit.preview:
			message_payload["excerpt"] = hit.preview[:300]
		return message_payload
	payload: dict[str, object] = {
		"type": "chat",
		"chat_id": str(thread.id),
		"title": thread.title or "",
	}
	if summary:
		payload["preview"] = str(summary)[:100]
	elif thread.messages:
		# no catalog summary yet - use last 3 user/assistant turns as preview
		turns = [
			m.text_content[:80]
			for m in sorted(thread.messages, key=lambda m: m.created_at)
			if m.type in (MessageType.USER, MessageType.ASSISTANT) and m.text_content
		][-3:]
		if turns:
			payload["preview"] = " | ".join(turns)
	return payload


def _chat_error(exc: HTTPException) -> str:
	return str(exc.detail).replace("Thread", "chat").replace("thread", "chat")


async def _load_message(
	message_id: TypeID,
	app_context: AppContext,
) -> Message:
	return await get_message(
		message_id,
		app_context.session,
		principal=app_context.principal,
	)


class ChatGetTool(Tool):
	"""search, list, and read chats."""

	name: str = Field(default="chat_get")
	description: str = Field(
		default=(
			"retrieve chats. provide query to search, chat_id to read a chat page, "
			"message_id to read around a message (optionally with before and after), "
			"or omit all three to list chats in the same order users see them. all "
			"search uses hybrid retrieval."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ChatGetInput.model_json_schema()
	)

	async def run(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		inp = ChatGetInput.model_validate(kwargs)
		try:
			if inp.query and (inp.chat_id or inp.message_id):
				return self.error(
					"provide query, chat_id, or message_id, not combinations",
					__tool_call_context__,
				)
			if inp.chat_id and inp.message_id:
				return self.error(
					"provide chat_id or message_id, not both",
					__tool_call_context__,
				)
			if inp.query:
				return await self._search(inp, __tool_call_context__, __app_context__)
			if inp.chat_id or inp.message_id:
				return await self._chat_page(
					inp, __tool_call_context__, __app_context__
				)
			return await self._list(inp, __tool_call_context__, __app_context__)
		except HTTPException as exc:
			return self.error(_chat_error(exc), __tool_call_context__)

	async def _list(
		self,
		inp: ChatGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		# the tool lists the caller's own inbox: exclude their archived chats
		# (unless asked) and their not-yet-accepted message requests.
		me_id = app_context.principal.user.id
		filters = ThreadListFilters(
			not_archived_by=None if inp.include_archived else me_id,
			not_invite_pending_for=me_id,
		)
		chats = await list_threads(
			app_context.session,
			principal=app_context.principal,
			filters=filters,
			skip=inp.skip,
			limit=inp.limit,
			sort_by="last_activity_at",
			sort_dir="desc",
		)
		total = await count_threads(
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
		return self.success(json.dumps(out), tool_call_context)

	async def _search(
		self,
		inp: ChatGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		if not inp.query:
			return self.error(
				"query is required when searching chats", tool_call_context
			)
		scored = await search_threads(
			inp.query,
			app_context.session,
			principal=app_context.principal,
			limit=inp.limit + 1,
			offset=inp.offset,
			search_params=_HYBRID_SEARCH,
		)
		has_more = len(scored) > inp.limit
		results = [
			_thread_search_result(scored_hit.item, scored_hit.hit)
			for scored_hit in scored[: inp.limit]
		]
		next_offset = inp.offset + inp.limit if has_more else None
		out: dict[str, object] = {
			"status": "success",
			"message": f"found {len(results)} chats",
			"count": len(results),
			"results": results,
			"next_offset": next_offset,
		}
		return self.success(
			json.dumps(out),
			tool_call_context,
			metadata=with_citable_sources(
				None,
				[
					citation_source(
						CitationSource.THREAD,
						hit.item.id,
						hit.item.title,
					)
					for hit in scored[: inp.limit]
				],
			),
		)

	async def _chat_page(
		self,
		inp: ChatGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		target_message_id = inp.message_id
		chat_id = inp.chat_id
		if target_message_id is not None:
			message = await _load_message(target_message_id, app_context)
			chat_id = message.thread_id
		if chat_id is None:
			return self.error("chat_id or message_id is required", tool_call_context)
		chat = await get_thread(
			chat_id,
			app_context.session,
			principal=app_context.principal,
		)
		payload = _chat_payload(chat)
		summaries = await self._summary_payloads(app_context, chat.id)
		if summaries:
			payload["summaries"] = summaries
		branch_page = await get_branch_page(
			chat.id,
			app_context.session,
			principal=app_context.principal,
			skip=inp.skip,
			limit=inp.limit,
			anchor_message_id=target_message_id,
			before=inp.before,
			after=inp.after,
		)
		message_results = [
			_message_payload(message) for message in branch_page.messages
		]
		out: dict[str, object] = {
			"status": "success",
			"message": "chat page retrieved",
			"chat": payload,
			"message_page": {
				"count": len(message_results),
				"total": branch_page.total,
				"skip": branch_page.skip,
				"limit": inp.limit,
				"has_more_older": branch_page.has_toward_root,
				"has_more_newer": branch_page.has_toward_leaf,
				"next_skip": branch_page.skip + len(message_results)
				if branch_page.has_toward_root
				else None,
				"previous_skip": max(branch_page.skip - inp.limit, 0)
				if branch_page.has_toward_leaf
				else None,
				"target_message_id": str(target_message_id)
				if target_message_id
				else None,
				"results": message_results,
			},
		}
		return self.success(
			json.dumps(out),
			tool_call_context,
			metadata=with_citable_sources(
				None, [citation_source(CitationSource.THREAD, chat.id, chat.title)]
			),
		)

	async def _summary_payloads(
		self,
		app_context: AppContext,
		chat_id: TypeID,
	) -> list[dict[str, object]]:
		summaries = await list_active_summaries(
			chat_id,
			app_context.session,
			purpose=SummaryPurpose.CATALOG,
		)
		return [_summary_payload(summary) for summary in summaries]
