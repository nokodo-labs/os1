"""reminders tools - get/search and create/edit reminders."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.models.reminder import Reminder as ReminderModel
from api.models.reminder import ReminderList as ReminderListModel
from api.models.reminder import ReminderStatus
from api.schemas.reminder import (
	Reminder,
	ReminderCreate,
	ReminderList,
	ReminderListWithCounts,
	ReminderUpdate,
	ReminderWithSubtasks,
)
from api.schemas.scheduled_item import Recurrence
from api.schemas.search import Page, SearchMode, SearchParams
from api.v1.service import reminders as reminder_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


_HYBRID_SEARCH = SearchParams(mode=SearchMode.HYBRID)
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 30

type ReminderPayloadSource = ReminderModel | Reminder | ReminderWithSubtasks
type ReminderListPayloadSource = (
	ReminderListModel | ReminderList | ReminderListWithCounts
)


class ReminderGetInput(BaseModel):
	"""input schema for reminder_get tool."""

	model_config = ConfigDict(extra="forbid")

	reminder_id: TypeID | None = Field(
		default=None,
		description="id of a specific reminder to fetch.",
	)
	list_id: TypeID | None = Field(
		default=None,
		description="id of a specific reminder list to fetch.",
	)
	query: str | None = Field(
		default=None,
		description=(
			"natural language query for hybrid search. "
			"also matches reminder lists by name and description."
		),
		min_length=1,
		max_length=500,
	)
	offset: int = Field(
		default=0,
		description="offset for reminder search pages.",
		ge=0,
	)
	skip: int = Field(
		default=0,
		description="offset for list pages.",
		ge=0,
	)
	limit: int = Field(
		default=_DEFAULT_LIMIT,
		description="maximum items to return per page. use skip or offset to continue.",
		ge=1,
		le=_MAX_LIMIT,
	)
	include_completed: bool = Field(
		default=False,
		description="include completed reminders when searching reminders.",
	)


class ReminderWriteInput(BaseModel):
	"""input schema for reminder_write tool."""

	model_config = ConfigDict(extra="forbid")

	reminder_id: TypeID | None = Field(
		default=None,
		description="ID of the reminder to edit or delete. omit to create one.",
	)
	list_id: TypeID | None = Field(
		default=None,
		description=(
			"target reminder list when creating or moving a reminder. omit on "
			"create to use the default reminder list."
		),
	)
	delete: bool = Field(
		default=False,
		description="delete the reminder identified by reminder_id.",
	)
	title: str | None = Field(
		default=None,
		description="title of the reminder. required when creating.",
		max_length=200,
	)
	description: str | None = Field(
		default=None,
		description="longer description or notes.",
	)
	parent_id: TypeID | None = Field(
		default=None,
		description="parent reminder id when creating or moving a subtask.",
	)
	position: float | None = Field(
		default=None,
		description=(
			"position for ordering within the reminder list. omit to append last."
		),
	)
	due_at: datetime | None = Field(
		default=None,
		description="due date/time in ISO 8601 format.",
	)
	remind_at: datetime | None = Field(
		default=None,
		description="notification time in ISO 8601 format.",
	)
	recurrence: Recurrence | None = Field(
		default=None,
		description=(
			"optional structured recurrence with rrule, rdate, exdate, and timezone."
		),
	)
	status: ReminderStatus | None = Field(
		default=None,
		description="status when editing.",
	)


class ReminderGetTool(Tool[AppContext]):
	"""fetch, list, or search reminders and reminder lists."""

	name: str = Field(default="reminder_get")
	description: str = Field(
		default=(
			"retrieve reminders and reminder lists. provide reminder_id to get one "
			"reminder with subtasks, list_id to get one list with counts, query to "
			"search reminders and lists, or omit all three to list reminder lists. "
			"reminder search uses hybrid retrieval."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ReminderGetInput.model_json_schema()
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
		inp = ReminderGetInput.model_validate(kwargs)
		provided = sum(
			value is not None for value in (inp.reminder_id, inp.list_id, inp.query)
		)
		if provided > 1:
			return self.error(
				"provide reminder_id, list_id, or query, not combinations",
				__tool_call_context__,
			)
		if inp.reminder_id is not None:
			return await self._get_reminder(inp, __tool_call_context__, __app_context__)
		if inp.list_id is not None:
			return await self._get_list(inp, __tool_call_context__, __app_context__)
		if inp.query is not None:
			return await self._search(inp, __tool_call_context__, __app_context__)
		return await self._list_lists(inp, __tool_call_context__, __app_context__)

	async def _get_reminder(
		self,
		inp: ReminderGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		if inp.reminder_id is None:
			return self.error("reminder_id is required", tool_call_context)
		try:
			reminder = await reminder_service.get_reminder(
				inp.reminder_id,
				app_context.session,
				principal=app_context.principal,
				with_subtasks=True,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		out = {
			"status": "success",
			"message": "reminder retrieved",
			"reminder": _reminder_payload(reminder, include_subtasks=True),
		}
		return self.success(json.dumps(out), tool_call_context)

	async def _get_list(
		self,
		inp: ReminderGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		if inp.list_id is None:
			return self.error("list_id is required", tool_call_context)
		try:
			reminder_list = await reminder_service.get_reminder_list(
				inp.list_id,
				app_context.session,
				principal=app_context.principal,
			)
			payload = await _reminder_list_payload(reminder_list, app_context)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		out = {
			"status": "success",
			"message": "reminder list retrieved",
			"list": payload,
		}
		return self.success(json.dumps(out), tool_call_context)

	async def _list_lists(
		self,
		inp: ReminderGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		try:
			lists = await reminder_service.list_reminder_lists(
				app_context.session,
				principal=app_context.principal,
				include_counts=True,
				skip=inp.skip,
				limit=inp.limit,
			)
			total = await reminder_service.count_reminder_lists(
				app_context.session,
				principal=app_context.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		results = [
			await _reminder_list_payload(reminder_list, app_context)
			for reminder_list in lists
		]
		next_skip = inp.skip + len(results) if inp.skip + len(results) < total else None
		out = {
			"status": "success",
			"message": f"found {len(results)} reminder lists",
			"count": len(results),
			"total": total,
			"skip": inp.skip,
			"limit": inp.limit,
			"has_more": next_skip is not None,
			"next_skip": next_skip,
			"results": results,
		}
		return self.success(json.dumps(out), tool_call_context)

	async def _search(
		self,
		inp: ReminderGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		if inp.query is None:
			return self.error("query is required", tool_call_context)
		try:
			lists = await reminder_service.search_reminder_lists(
				inp.query,
				app_context.session,
				principal=app_context.principal,
				offset=inp.offset,
				limit=inp.limit,
			)
			list_results = [
				await _reminder_list_payload(reminder_list, app_context)
				for reminder_list in lists
			]
			scored = await reminder_service.search_reminders(
				inp.query,
				app_context.session,
				principal=app_context.principal,
				limit=inp.limit + 1,
				offset=inp.offset,
				search_params=_HYBRID_SEARCH,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		page = Page(
			items=[hit.item for hit in scored[: inp.limit]],
			has_more=len(scored) > inp.limit,
		)
		reminder_items = page.items
		if not inp.include_completed:
			reminder_items = [
				item
				for item in reminder_items
				if item.status != ReminderStatus.COMPLETED
			]
		reminder_results = [_reminder_search_result(item) for item in reminder_items]
		next_offset = inp.offset + inp.limit if page.has_more else None
		out = {
			"status": "success",
			"message": "reminder search complete",
			"reminder_lists": list_results,
			"reminders": reminder_results,
			"list_count": len(list_results),
			"reminder_count": len(reminder_results),
			"next_offset": next_offset,
		}
		return self.success(json.dumps(out), tool_call_context)


class ReminderWriteTool(Tool[AppContext]):
	"""create, edit, or delete reminders."""

	name: str = Field(default="reminder_write")
	description: str = Field(
		default=(
			"create, edit, complete, or delete reminders. omit reminder_id to "
			"create a reminder. provide list_id to place a new reminder in a "
			"specific reminder list; otherwise the default list is used."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ReminderWriteInput.model_json_schema()
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
		inp = ReminderWriteInput.model_validate(kwargs)

		if inp.delete:
			return await self._delete(inp, __tool_call_context__, __app_context__)
		if inp.reminder_id is not None:
			return await self._update(inp, __tool_call_context__, __app_context__)
		return await self._create(inp, __tool_call_context__, __app_context__)

	async def _delete(
		self,
		inp: ReminderWriteInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		if inp.reminder_id is None:
			return self.error(
				"reminder_id is required when deleting",
				tool_call_context,
			)
		try:
			await reminder_service.delete_reminder(
				inp.reminder_id,
				app_context.session,
				principal=app_context.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		out = {
			"status": "success",
			"message": "reminder deleted",
			"id": str(inp.reminder_id),
		}
		return self.success(json.dumps(out), tool_call_context)

	async def _update(
		self,
		inp: ReminderWriteInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		if inp.reminder_id is None:
			return self.error("reminder_id is required", tool_call_context)
		update_kwargs: dict[str, object] = {}
		if inp.title is not None:
			update_kwargs["title"] = inp.title
		if inp.description is not None:
			update_kwargs["description"] = inp.description
		if inp.due_at is not None:
			update_kwargs["due_at"] = inp.due_at
		if inp.remind_at is not None:
			update_kwargs["remind_at"] = inp.remind_at
		if inp.recurrence is not None:
			update_kwargs["recurrence"] = inp.recurrence
		if inp.list_id is not None:
			update_kwargs["list_id"] = inp.list_id
		if inp.parent_id is not None:
			update_kwargs["parent_id"] = inp.parent_id
		if inp.position is not None:
			update_kwargs["position"] = inp.position
		if inp.status is not None:
			update_kwargs["status"] = inp.status

		if update_kwargs == {"status": ReminderStatus.COMPLETED}:
			try:
				reminder = await reminder_service.complete_reminder(
					inp.reminder_id,
					app_context.session,
					principal=app_context.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), tool_call_context)
			out = {
				"status": "success",
				"message": "reminder completed",
				"id": str(reminder.id),
			}
			return self.success(json.dumps(out), tool_call_context)

		try:
			reminder = await reminder_service.update_reminder(
				inp.reminder_id,
				ReminderUpdate.model_validate(update_kwargs),
				app_context.session,
				principal=app_context.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		out = {
			"status": "success",
			"message": "reminder updated",
			"id": str(reminder.id),
		}
		return self.success(json.dumps(out), tool_call_context)

	async def _create(
		self,
		inp: ReminderWriteInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		if not inp.title:
			return self.error(
				"title is required when creating a reminder",
				tool_call_context,
			)
		try:
			create_kwargs: dict[str, object] = {
				"title": inp.title,
				"description": inp.description,
				"due_at": inp.due_at,
				"remind_at": inp.remind_at,
				"recurrence": inp.recurrence,
				"list_id": inp.list_id,
				"parent_id": inp.parent_id,
			}
			if inp.position is not None:
				create_kwargs["position"] = inp.position
			reminder = await reminder_service.create_reminder(
				ReminderCreate.model_validate(create_kwargs),
				app_context.session,
				principal=app_context.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		out = {
			"status": "success",
			"message": "reminder created",
			"id": str(reminder.id),
			"list_id": str(reminder.list_id),
		}
		return self.success(json.dumps(out), tool_call_context)


def _reminder_search_result(reminder: ReminderModel) -> dict[str, object]:
	"""summarize a reminder for agent search results."""
	return {
		"id": str(reminder.id),
		"title": reminder.title,
		**({"description": reminder.description} if reminder.description else {}),
	}


def _reminder_payload(
	reminder: ReminderPayloadSource,
	include_subtasks: bool,
) -> dict[str, object]:
	payload: dict[str, object] = {
		"id": str(reminder.id),
		"title": reminder.title,
		"reminder_status": reminder.status.value,
		"list_id": str(reminder.list_id),
		"position": reminder.position,
	}
	if reminder.description:
		payload["description"] = reminder.description
	if reminder.due_at:
		payload["due_at"] = reminder.due_at.isoformat()
	if reminder.remind_at:
		payload["remind_at"] = reminder.remind_at.isoformat()
	if reminder.completed_at:
		payload["completed_at"] = reminder.completed_at.isoformat()
	if reminder.parent_id:
		payload["parent_id"] = str(reminder.parent_id)
	if include_subtasks:
		subtasks = reminder.subtasks if isinstance(reminder, ReminderModel) else []
		if isinstance(reminder, ReminderWithSubtasks):
			subtasks = reminder.subtasks
		payload["subtasks"] = [
			_reminder_payload(subtask, include_subtasks=False) for subtask in subtasks
		]
	return payload


async def _reminder_list_payload(
	reminder_list: ReminderListPayloadSource,
	app_context: AppContext,
) -> dict[str, object]:
	payload: dict[str, object] = {
		"id": str(reminder_list.id),
		"name": reminder_list.name,
		"description": reminder_list.description,
		"color": reminder_list.color,
		"icon": reminder_list.icon,
		"position": reminder_list.position,
		"is_default": reminder_list.is_default,
		"project_ids": [str(project_id) for project_id in reminder_list.project_ids],
		"created_at": reminder_list.created_at.isoformat(),
		"updated_at": reminder_list.updated_at.isoformat(),
	}
	if isinstance(reminder_list, ReminderListWithCounts):
		counts = {
			"total_count": reminder_list.total_count,
			"pending_count": reminder_list.pending_count,
			"completed_count": reminder_list.completed_count,
		}
	else:
		counts = await reminder_service.get_list_counts(
			app_context.session,
			principal=app_context.principal,
			list_id=reminder_list.id,
		)
	payload.update(counts)
	return payload
