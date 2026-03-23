"""reminders tools - get/search and create/edit reminders."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.models.reminder import ReminderStatus
from api.schemas.reminder import ReminderCreate, ReminderUpdate
from api.v1.service import reminders as reminder_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class ReminderGetInput(BaseModel):
	"""input schema for reminder_get tool.

	provide reminder_id to fetch a specific reminder, or query to search.
	"""

	model_config = ConfigDict(extra="forbid")

	reminder_id: str | None = Field(
		default=None,
		description=(
			"ID of a specific reminder to fetch. when provided, query is ignored."
		),
	)
	query: str | None = Field(
		default=None,
		description=(
			"natural language search query. required when reminder_id is not given. "
			"hybrid BM25 + semantic search is used."
		),
	)
	limit: int = Field(
		default=5,
		description="max reminders to return when searching (ignored for direct fetch)",
		ge=1,
		le=20,
	)


class ReminderWriteInput(BaseModel):
	"""input schema for reminder_write tool.

	provide reminder_id to update an existing reminder, or omit to create a new one.
	"""

	model_config = ConfigDict(extra="forbid")

	reminder_id: str | None = Field(
		default=None,
		description="ID of the reminder to edit. omit to create a new reminder.",
	)
	title: str | None = Field(
		default=None,
		description="title of the reminder. required when creating.",
		max_length=200,
	)
	description: str | None = Field(
		default=None,
		description="longer description or notes",
	)
	due_at: datetime | None = Field(
		default=None,
		description="due date/time in ISO 8601 format",
	)
	remind_at: datetime | None = Field(
		default=None,
		description="notification time in ISO 8601 format",
	)
	status: Literal["pending", "completed"] | None = Field(
		default=None,
		description="status when editing: 'pending' or 'completed'",
	)


class ReminderGetTool(Tool[AppContext]):
	"""fetch a specific reminder by ID or search reminders by query."""

	name: str = Field(default="reminder_get")
	description: str = Field(
		default=(
			"retrieve reminders. provide reminder_id to get a specific reminder with "
			"full details, or provide a query to search reminders by meaning."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ReminderGetInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = ReminderGetInput.model_validate(kwargs)

		if inp.reminder_id:
			# direct fetch by ID
			try:
				reminder = await reminder_service.get_reminder(
					TypeID(inp.reminder_id),
					__app_context__.session,
					principal=__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __agent_context__)
			result: dict[str, object] = {
				"status": "success",
				"message": "reminder retrieved",
				"id": str(reminder.id),
				"title": reminder.title,
				"reminder_status": reminder.status.value,
			}
			if reminder.description:
				result["description"] = reminder.description
			if reminder.due_at:
				result["due_at"] = reminder.due_at.isoformat()
			if reminder.remind_at:
				result["remind_at"] = reminder.remind_at.isoformat()
			if reminder.completed_at:
				result["completed_at"] = reminder.completed_at.isoformat()
			return self.success(json.dumps(result), __agent_context__)

		if not inp.query:
			return self.error(
				"provide reminder_id to fetch a reminder or query to search",
				__agent_context__,
			)

		# search by query
		try:
			page = await reminder_service.search_reminders(
				inp.query,
				__app_context__.session,
				principal=__app_context__.principal,
				limit=inp.limit,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __agent_context__)

		if not page.items:
			out = {
				"status": "success",
				"message": "no reminders found",
				"count": 0,
				"results": [],
			}
			return self.success(json.dumps(out), __agent_context__)

		results = [
			{
				"id": item.id,
				"title": item.title,
				**({"description": item.preview} if item.preview else {}),
			}
			for item in page.items
		]
		n = len(results)
		msg = f"found {n} {'reminder' if n == 1 else 'reminders'}"
		out = {"status": "success", "message": msg, "count": n, "results": results}
		return self.success(json.dumps(out), __agent_context__)


class ReminderWriteTool(Tool[AppContext]):
	"""create a new reminder or edit an existing one."""

	name: str = Field(default="reminder_write")
	description: str = Field(
		default=(
			"create or edit a reminder. omit reminder_id to create a new reminder "
			"(title required). provide reminder_id to update an existing reminder's "
			"title, description, due date, notification time, or status."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ReminderWriteInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = ReminderWriteInput.model_validate(kwargs)

		if inp.reminder_id:
			# update existing reminder
			rid = TypeID(inp.reminder_id)
			# use the dedicated complete endpoint when only completing
			if inp.status == "completed" and not any(
				[inp.title, inp.description, inp.due_at, inp.remind_at]
			):
				try:
					reminder = await reminder_service.complete_reminder(
						rid,
						__app_context__.session,
						principal=__app_context__.principal,
					)
				except HTTPException as exc:
					return self.error(str(exc.detail), __agent_context__)
				out = {
					"status": "success",
					"message": "reminder completed",
					"id": str(reminder.id),
				}
				return self.success(json.dumps(out), __agent_context__)
			# general update - only include fields the agent actually provided
			update_kwargs: dict = {}
			if inp.title is not None:
				update_kwargs["title"] = inp.title
			if inp.description is not None:
				update_kwargs["description"] = inp.description
			if inp.due_at is not None:
				update_kwargs["due_at"] = inp.due_at
			if inp.remind_at is not None:
				update_kwargs["remind_at"] = inp.remind_at
			if inp.status is not None and inp.status != "completed":
				update_kwargs["status"] = ReminderStatus(inp.status)
			try:
				reminder = await reminder_service.update_reminder(
					rid,
					ReminderUpdate(**update_kwargs),
					__app_context__.session,
					principal=__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __agent_context__)
			out = {
				"status": "success",
				"message": "reminder updated",
				"id": str(reminder.id),
			}
			return self.success(json.dumps(out), __agent_context__)

		# create new reminder
		if not inp.title:
			return self.error(
				"title is required when creating a reminder", __agent_context__
			)
		try:
			reminder = await reminder_service.create_reminder(
				ReminderCreate(
					title=inp.title,
					description=inp.description,
					due_at=inp.due_at,
					remind_at=inp.remind_at,
				),
				__app_context__.session,
				principal=__app_context__.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __agent_context__)
		out = {
			"status": "success",
			"message": "reminder created",
			"id": str(reminder.id),
		}
		return self.success(json.dumps(out), __agent_context__)
