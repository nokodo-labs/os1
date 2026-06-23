"""calendar tools - get/search and create/edit calendar events."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.models.calendar import CalendarEvent
from api.schemas.calendar import (
	CalendarEventCreate,
	CalendarEventUpdate,
)
from api.schemas.scheduled_item import Recurrence, ScheduledItem
from api.schemas.search import Page, SearchMode, SearchParams
from api.v1.service import calendar as calendar_service
from api.v1.service.calendar.events import list_calendar_scheduled_items
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.message_metadata import CITABLE_SOURCES_KEY
from api.v1.service.reminders.core import list_reminder_scheduled_items
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.typeid import TypeID


_HYBRID_SEARCH = SearchParams(mode=SearchMode.HYBRID)
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 30
_DEFAULT_UPCOMING_DAYS = 14


class CalendarEventGetInput(BaseModel):
	"""input schema for calendar_event_get tool."""

	model_config = ConfigDict(extra="forbid")

	calendar_event_id: str | None = Field(
		default=None,
		description="ID of a specific calendar event to fetch.",
	)
	query: str | None = Field(
		default=None,
		description="natural language query for hybrid search of calendar events.",
		min_length=1,
		max_length=500,
	)
	start_at: datetime | None = Field(
		default=None,
		description=(
			"optional inclusive scheduled-items window start in ISO 8601 format"
		),
	)
	end_at: datetime | None = Field(
		default=None,
		description="optional inclusive scheduled-items window end in ISO 8601 format",
	)
	offset: int = Field(
		default=0,
		description="number of calendar event search results to skip before this page.",
		ge=0,
	)
	skip: int = Field(
		default=0,
		description="offset for scheduled-item pages.",
		ge=0,
	)
	limit: int = Field(
		default=_DEFAULT_LIMIT,
		description="maximum items to return per page. use skip or offset to continue.",
		ge=1,
		le=_MAX_LIMIT,
	)


class CalendarEventWriteInput(BaseModel):
	"""input schema for calendar_event_write tool."""

	model_config = ConfigDict(extra="forbid")

	calendar_event_id: str | None = Field(
		default=None,
		description="ID of the event to edit or delete. omit to create a new event.",
	)
	delete: bool = Field(
		default=False,
		description="delete the event identified by calendar_event_id",
	)
	title: str | None = Field(
		default=None,
		description="event title. required when creating.",
		max_length=200,
	)
	description: str | None = Field(
		default=None,
		description="event details or agenda",
	)
	start_at: datetime | None = Field(
		default=None,
		description="event start in ISO 8601 format. required when creating.",
	)
	end_at: datetime | None = Field(
		default=None,
		description="event end in ISO 8601 format. required when creating.",
	)
	all_day: bool | None = Field(
		default=None,
		description="true for an all-day event",
	)
	calendar_id: str | None = Field(
		default=None,
		description=(
			"target calendar ID when creating. when editing or deleting, this scopes "
			"the event lookup to that calendar. omit to use the default calendar "
			"on create."
		),
	)
	timezone: str | None = Field(
		default=None,
		description="event timezone name",
		max_length=64,
	)
	recurrence: Recurrence | None = Field(
		default=None,
		description=(
			"optional structured recurrence with rrule, rdate, exdate, and timezone"
		),
	)
	notification_offsets: list[int] | None = Field(
		default=None,
		description="notification offsets in minutes before start",
		max_length=8,
	)
	location: str | None = Field(
		default=None,
		description="physical place or room. mutually exclusive with virtual_url.",
		max_length=255,
	)
	virtual_url: str | None = Field(
		default=None,
		description="meeting link. mutually exclusive with location.",
		max_length=512,
	)
	labels: list[str] | None = Field(
		default=None,
		description="label strings to tag the event",
	)

	@model_validator(mode="after")
	def _validate_place(self) -> CalendarEventWriteInput:
		if self.location and self.virtual_url:
			raise ValueError("location and virtual_url are mutually exclusive")
		return self


def _calendar_event_search_result(event: CalendarEvent) -> dict[str, object]:
	"""summarize a calendar event for agent search results."""
	return {
		"id": str(event.id),
		"title": event.title or "",
		**({"preview": event.description[:100]} if event.description else {}),
	}


def _event_payload(calendar_event: CalendarEvent) -> dict[str, object]:
	"""serialize one calendar event for tool output."""
	return {
		"id": str(calendar_event.id),
		"title": calendar_event.title,
		"start_at": calendar_event.start_at.isoformat(),
		"end_at": calendar_event.end_at.isoformat(),
		"all_day": calendar_event.all_day,
		"calendar_id": str(calendar_event.calendar_id),
		"notification_offsets": list(calendar_event.notification_offsets or []),
		"labels": list(calendar_event.labels or []),
		**(
			{"description": calendar_event.description}
			if calendar_event.description
			else {}
		),
		**({"timezone": calendar_event.timezone} if calendar_event.timezone else {}),
		**(
			{"recurrence": calendar_event.recurrence}
			if calendar_event.recurrence
			else {}
		),
		**({"location": calendar_event.location} if calendar_event.location else {}),
		**(
			{"virtual_url": calendar_event.virtual_url}
			if calendar_event.virtual_url
			else {}
		),
	}


def _scheduled_item_payload(item: ScheduledItem) -> dict[str, object]:
	"""serialize one scheduled reminder or calendar occurrence for tool output."""
	status = item.status if isinstance(item.status, str) else item.status.value
	payload: dict[str, object] = {
		"type": "reminder" if item.kind == "reminder" else "calendar_event",
		"id": str(item.parent_id),
		"occurrence_id": item.id,
		"original_occurrence_at": item.original_occurrence_at.isoformat(),
		"effective_start_at": item.effective_start_at.isoformat(),
		"title": item.title,
		"status": status,
		"readonly": item.readonly,
	}
	if item.effective_end_at is not None:
		payload["effective_end_at"] = item.effective_end_at.isoformat()
	if item.description is not None:
		payload["description"] = item.description
	if item.color is not None:
		payload["color"] = item.color
	if item.all_day:
		payload["all_day"] = item.all_day
	if item.completed_at is not None:
		payload["completed_at"] = item.completed_at.isoformat()
	if item.kind == "reminder":
		payload["reminder_id"] = str(item.parent_id)
		if item.reminder_list_id is not None:
			payload["reminder_list_id"] = str(item.reminder_list_id)
	elif item.kind == "event":
		payload["calendar_event_id"] = str(item.parent_id)
		if item.calendar_id is not None:
			payload["calendar_id"] = str(item.calendar_id)
	return payload


def _citable_source(
	source_type: str, source_id: object, title: str | None
) -> JSONValue:
	"""build one citation-source payload for concrete scheduled resources."""
	return {
		"source_type": source_type,
		"source_id": str(source_id),
		"title": title,
	}


def _calendar_event_citable_sources(calendar_event: CalendarEvent) -> list[JSONValue]:
	"""return the event and owning calendar citation sources for an event."""
	return [
		_citable_source("calendar_event", calendar_event.id, calendar_event.title),
		_citable_source("calendar", calendar_event.calendar_id, calendar_event.title),
	]


def _scheduled_item_citable_sources(item: ScheduledItem) -> list[JSONValue]:
	"""return citation sources represented by one scheduled item."""
	sources: list[JSONValue] = []
	if item.kind == "reminder":
		sources.append(_citable_source("reminder", item.parent_id, item.title))
		if item.reminder_list_id is not None:
			sources.append(
				_citable_source("reminder_list", item.reminder_list_id, item.title)
			)
	elif item.kind == "event":
		sources.append(_citable_source("calendar_event", item.parent_id, item.title))
		if item.calendar_id is not None:
			sources.append(_citable_source("calendar", item.calendar_id, item.title))
	return sources


def _success_with_citations(
	output: dict[str, object],
	tool_call_context: ToolCallContext,
	citable_sources: list[JSONValue],
) -> ToolMessage:
	"""return a tool success message carrying citation metadata."""
	return ToolMessage(
		tool_call_id=tool_call_context.tool_call_id,
		tool_output=json.dumps(output),
		metadata={CITABLE_SOURCES_KEY: citable_sources},
	)


class CalendarEventGetTool(Tool[AppContext]):
	"""fetch an event, search events, or list upcoming scheduled items."""

	name: str = Field(default="calendar_event_get")
	description: str = Field(
		default=(
			"retrieve calendar information. provide calendar_event_id to get one "
			"calendar event, query to search calendar events, or omit both to "
			"return upcoming scheduled items from calendars and reminder lists."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: CalendarEventGetInput.model_json_schema()
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
		inp = CalendarEventGetInput.model_validate(kwargs)
		if inp.calendar_event_id and inp.query:
			return self.error(
				"provide calendar_event_id or query, not both",
				__tool_call_context__,
			)

		try:
			if inp.calendar_event_id:
				calendar_event = await calendar_service.get_calendar_event(
					TypeID(inp.calendar_event_id),
					__app_context__.session,
					principal=__app_context__.principal,
				)
				out: dict[str, object] = {
					"status": "success",
					"message": "calendar event retrieved",
					"event": _event_payload(calendar_event),
				}
				return _success_with_citations(
					out,
					__tool_call_context__,
					_calendar_event_citable_sources(calendar_event),
				)

			if inp.query:
				scored = await calendar_service.search_calendar_events(
					inp.query,
					__app_context__.session,
					principal=__app_context__.principal,
					limit=inp.limit + 1,
					offset=inp.offset,
					search_params=_HYBRID_SEARCH,
				)
				page = Page(
					items=[hit.item for hit in scored[: inp.limit]],
					has_more=len(scored) > inp.limit,
				)
				search_results = [
					_calendar_event_search_result(item) for item in page.items
				]
				next_offset = inp.offset + inp.limit if page.has_more else None
				search_out: dict[str, object] = {
					"status": "success",
					"message": f"found {len(search_results)} calendar events",
					"count": len(search_results),
					"next_offset": next_offset,
					"results": search_results,
				}
				return _success_with_citations(
					search_out,
					__tool_call_context__,
					[
						_citable_source("calendar_event", item.id, item.title)
						for item in page.items
					],
				)
		except HTTPException as exc:
			return self.error(str(exc.detail), __tool_call_context__)

		return await self._scheduled_items(inp, __tool_call_context__, __app_context__)

	async def _scheduled_items(
		self,
		inp: CalendarEventGetInput,
		tool_call_context: ToolCallContext,
		app_context: AppContext,
	) -> ToolMessage:
		"""return a merged scheduled-item page for calendars and reminders."""
		start_at = inp.start_at or datetime.now(tz=UTC)
		end_at = inp.end_at or start_at + timedelta(days=_DEFAULT_UPCOMING_DAYS)
		if end_at <= start_at:
			return self.error("end_at must be after start_at", tool_call_context)
		try:
			items = [
				*(
					await list_calendar_scheduled_items(
						app_context.session,
						app_context.principal,
						start_at,
						end_at,
					)
				),
				*(
					await list_reminder_scheduled_items(
						app_context.session,
						app_context.principal,
						start_at,
						end_at,
						include_completed=True,
					)
				),
			]
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		items.sort(
			key=lambda item: (
				item.effective_start_at,
				item.kind,
				str(item.parent_id),
			)
		)
		page = items[inp.skip : inp.skip + inp.limit]
		results = [_scheduled_item_payload(item) for item in page]
		citable_sources: list[JSONValue] = []
		for item in page:
			citable_sources.extend(_scheduled_item_citable_sources(item))
		next_skip = (
			inp.skip + len(results) if inp.skip + len(results) < len(items) else None
		)
		out: dict[str, object] = {
			"status": "success",
			"message": f"found {len(results)} scheduled items",
			"count": len(results),
			"window_start_at": start_at.isoformat(),
			"window_end_at": end_at.isoformat(),
			"skip": inp.skip,
			"limit": inp.limit,
			"has_more": next_skip is not None,
			"next_skip": next_skip,
			"results": results,
		}
		return _success_with_citations(out, tool_call_context, citable_sources)


class CalendarEventWriteTool(Tool[AppContext]):
	"""create, edit, or delete a calendar event."""

	name: str = Field(default="calendar_event_write")
	description: str = Field(
		default=(
			"create, edit, or delete calendar events. omit calendar_event_id "
			"to create. "
			"provide calendar_event_id to update or set delete=true to delete."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: CalendarEventWriteInput.model_json_schema()
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
		inp = CalendarEventWriteInput.model_validate(kwargs)

		if inp.delete:
			if not inp.calendar_event_id:
				return self.error(
					"calendar_event_id is required when deleting",
					__tool_call_context__,
				)
			try:
				await calendar_service.delete_calendar_event(
					TypeID(inp.calendar_event_id),
					__app_context__.session,
					principal=__app_context__.principal,
					calendar_id=TypeID(inp.calendar_id) if inp.calendar_id else None,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __tool_call_context__)
			delete_out: dict[str, object] = {
				"status": "success",
				"message": "calendar event deleted",
				"id": inp.calendar_event_id,
			}
			return self.success(json.dumps(delete_out), __tool_call_context__)

		if inp.calendar_event_id:
			update_kwargs: dict[str, object] = {}
			if inp.title is not None:
				update_kwargs["title"] = inp.title
			if inp.description is not None:
				update_kwargs["description"] = inp.description
			if inp.start_at is not None:
				update_kwargs["start_at"] = inp.start_at
			if inp.end_at is not None:
				update_kwargs["end_at"] = inp.end_at
			if inp.all_day is not None:
				update_kwargs["all_day"] = inp.all_day
			if inp.timezone is not None:
				update_kwargs["timezone"] = inp.timezone
			if inp.recurrence is not None:
				update_kwargs["recurrence"] = inp.recurrence
			if inp.notification_offsets is not None:
				update_kwargs["notification_offsets"] = inp.notification_offsets
			if inp.location is not None:
				update_kwargs["location"] = inp.location
			if inp.virtual_url is not None:
				update_kwargs["virtual_url"] = inp.virtual_url
			if inp.labels is not None:
				update_kwargs["labels"] = inp.labels
			try:
				calendar_event = await calendar_service.update_calendar_event(
					TypeID(inp.calendar_event_id),
					CalendarEventUpdate.model_validate(update_kwargs),
					__app_context__.session,
					principal=__app_context__.principal,
					calendar_id=TypeID(inp.calendar_id) if inp.calendar_id else None,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __tool_call_context__)
			update_out: dict[str, object] = {
				"status": "success",
				"message": "calendar event updated",
				"event": _event_payload(calendar_event),
			}
			return self.success(json.dumps(update_out), __tool_call_context__)

		if not inp.title or inp.start_at is None or inp.end_at is None:
			return self.error(
				"title, start_at, and end_at are required when creating an event",
				__tool_call_context__,
			)
		try:
			calendar_event = await calendar_service.create_calendar_event(
				CalendarEventCreate(
					title=inp.title,
					description=inp.description,
					start_at=inp.start_at,
					end_at=inp.end_at,
					all_day=inp.all_day or False,
					timezone=inp.timezone,
					recurrence=inp.recurrence,
					notification_offsets=inp.notification_offsets or [],
					location=inp.location,
					virtual_url=inp.virtual_url,
					labels=inp.labels or [],
				),
				__app_context__.session,
				principal=__app_context__.principal,
				calendar_id=TypeID(inp.calendar_id) if inp.calendar_id else None,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __tool_call_context__)
		create_out: dict[str, object] = {
			"status": "success",
			"message": "calendar event created",
			"event": _event_payload(calendar_event),
		}
		return self.success(json.dumps(create_out), __tool_call_context__)
