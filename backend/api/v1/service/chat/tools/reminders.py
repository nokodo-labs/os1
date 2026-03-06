"""reminders tools - get/search and create/edit reminders."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

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
			parts = [f"title: {reminder.title}"]
			if reminder.description:
				parts.append(f"description: {reminder.description}")
			parts.append(f"status: {reminder.status.value}")
			if reminder.due_at:
				parts.append(f"due: {reminder.due_at.isoformat()}")
			if reminder.remind_at:
				parts.append(f"remind at: {reminder.remind_at.isoformat()}")
			if reminder.completed_at:
				parts.append(f"completed: {reminder.completed_at.isoformat()}")
			return self.success("\n".join(parts), __agent_context__)

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
			return self.success(
				"no reminders found matching the query", __agent_context__
			)

		lines = []
		for item in page.items:
			subtitle = f" - {item.subtitle}" if item.subtitle else ""
			lines.append(f"- [{item.id}] {item.title}{subtitle}")
		return self.success("\n".join(lines), __agent_context__)


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
			status = ReminderStatus(inp.status) if inp.status else None
			try:
				reminder = await reminder_service.update_reminder(
					TypeID(inp.reminder_id),
					ReminderUpdate(
						title=inp.title,
						description=inp.description,
						due_at=inp.due_at,
						remind_at=inp.remind_at,
						status=status,
					),
					__app_context__.session,
					principal=__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __agent_context__)
			return self.success(
				f"reminder updated: [{reminder.id}] {reminder.title}",
				__agent_context__,
			)

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
		due = f" (due: {reminder.due_at.isoformat()})" if reminder.due_at else ""
		return self.success(
			f"reminder created: [{reminder.id}] {reminder.title}{due}",
			__agent_context__,
		)
