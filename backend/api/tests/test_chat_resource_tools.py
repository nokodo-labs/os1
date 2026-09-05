"""behavior tests for backend chat resource tools."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.calendar import Calendar as CalendarModel
from api.models.calendar import CalendarEvent
from api.models.event import Event
from api.models.message import Message, MessageType, UserMessage
from api.models.reminder import Reminder as ReminderModel
from api.models.reminder import ReminderList as ReminderListModel
from api.models.reminder import ReminderStatus
from api.schemas.reminder import Reminder
from api.schemas.scheduled_item import ScheduledItem
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResourceReferenceType,
	SearchResultAnchor,
	SearchResultItem,
	SearchResultType,
)
from api.tests.factories import make_principal
from api.v1.service.authentication import Principal
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.tools.calendar import (
	CalendarEventGetTool,
	CalendarEventWriteTool,
)
from api.v1.service.chat.tools.chats import ChatGetTool
from api.v1.service.chat.tools.files import FileGetTool
from api.v1.service.chat.tools.memories import MemoryRecallTool
from api.v1.service.chat.tools.notes import NoteGetTool
from api.v1.service.chat.tools.projects import ProjectGetTool
from api.v1.service.chat.tools.reminders import ReminderGetTool, ReminderWriteTool
from api.v1.service.chat.tools.resource_search import ResourceSearchTool
from api.v1.service.files import FileContentChunkHit, FileContentLines
from api.v1.service.search.primitives import ScoredResult, SearchHit
from api.v1.service.threads import BranchPage
from nokodo_ai import AgentContext, AgentIterationSnapshot, AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import ToolCallContext
from nokodo_ai.threads import Thread
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _state() -> AgentIterationSnapshot[AppContext]:
	return AgentIterationState[AppContext](thread=Thread(), tools=[]).snapshot()


def _agent_context() -> AgentContext:
	return AgentContext(model=ChatModel.model_construct(model_name="stub"))


def _tool_call_context(tool_call_id: str = "tool-call") -> ToolCallContext:
	return ToolCallContext(
		tool_call_id=tool_call_id,
		tool_call_start_time=0.0,
	)


async def _noop_event_emitter(event: Event) -> None:
	_ = event


def _app_context() -> AppContext:
	return AppContext(
		session=AsyncSession(),
		principal=make_principal(slug="resource_tools_user", is_superuser=True),
		event_emitter=_noop_event_emitter,
	)


def _scored_item(
	result_type: SearchResultType,
	item_id: TypeID,
	title: str,
	preview: str = "preview",
) -> list[ScoredResult]:
	now = datetime.now(tz=UTC)
	item = SimpleNamespace(
		id=item_id,
		title=title,
		content=preview,
		name=title,
		description=preview,
		filename=title,
		mime_type="application/octet-stream",
		size_bytes=0,
		created_at=now,
		updated_at=now,
	)
	return [ScoredResult(item=item, score=0.9)]


def _citable_sources(message: object) -> list[dict[str, object]]:
	metadata = getattr(message, "metadata")
	assert isinstance(metadata, dict)
	sources = metadata.get("_citable_sources")
	assert isinstance(sources, list)
	assert all(isinstance(source, dict) for source in sources)
	return sources


@pytest.mark.asyncio
async def test_calendar_get_returns_upcoming_reminders_with_reminder_ids() -> None:
	now = datetime.now(tz=UTC)
	reminder_id = new_typeid("rem")
	list_id = new_typeid("remlst")
	item = ScheduledItem(
		kind="reminder",
		id=f"reminder:{reminder_id}:{now.isoformat()}",
		parent_id=reminder_id,
		container_id=list_id,
		reminder_list_id=list_id,
		original_occurrence_at=now,
		effective_start_at=now,
		title="send draft",
		status=ReminderStatus.COMPLETED,
		readonly=True,
		completed_at=now + timedelta(minutes=5),
	)
	app_context = _app_context()
	tool = CalendarEventGetTool()

	try:
		with (
			patch(
				"api.v1.service.chat.tools.calendar.list_calendar_scheduled_items",
				new=AsyncMock(return_value=[]),
			) as calendar_items,
			patch(
				"api.v1.service.chat.tools.calendar.list_reminder_scheduled_items",
				new=AsyncMock(return_value=[item]),
			) as reminder_items,
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
			)
	finally:
		await app_context.session.close()

	calendar_items.assert_awaited_once()
	reminder_items.assert_awaited_once()
	reminder_await = reminder_items.await_args
	assert reminder_await is not None
	assert reminder_await.kwargs["include_completed"] is True
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["count"] == 1
	assert payload["results"][0]["type"] == "reminder"
	assert payload["results"][0]["id"] == str(reminder_id)
	assert payload["results"][0]["occurrence_id"] == item.id
	assert payload["results"][0]["reminder_id"] == str(reminder_id)
	assert payload["results"][0]["reminder_list_id"] == str(list_id)
	assert "calendar_id" not in payload["results"][0]
	assert payload["results"][0]["status"] == ReminderStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_calendar_get_query_uses_container_search() -> None:
	"""the tool returns the anchored/anchorless container search union."""
	now = datetime.now(tz=UTC)
	calendar_id = new_typeid("cal")
	app_context = _app_context()
	tool = CalendarEventGetTool()
	calendar = CalendarModel(
		id=calendar_id,
		owner_id=app_context.principal.user.id,
		name="work calendar",
		color="#d45446",
		is_default=False,
	)
	event = CalendarEvent(
		id=new_typeid("calev"),
		owner_id=app_context.principal.user.id,
		calendar_id=calendar_id,
		title="planning sync",
		start_at=now,
		end_at=now + timedelta(hours=1),
		recurrence=None,
	)
	scored_hits = [
		ScoredResult(item=event, score=0.9),
		ScoredResult(item=calendar, score=0.4),
	]

	try:
		with (
			patch(
				"api.v1.service.chat.tools.calendar.search_calendars",
				new=AsyncMock(return_value=scored_hits),
			) as search,
			patch(
				"api.v1.service.chat.tools.calendar.load_calendars",
				new=AsyncMock(return_value={calendar_id: calendar}),
			),
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="planning",
				limit=7,
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "planning"
	assert search_await.kwargs["limit"] == 8
	assert search_await.kwargs["offset"] == 0
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["count"] == 2
	assert payload["next_offset"] is None
	anchored_out, anchorless_out = payload["results"]
	assert anchored_out["type"] == "calendar_event"
	assert anchored_out["id"] == str(event.id)
	assert anchored_out["title"] == "planning sync"
	assert anchored_out["calendar_id"] == str(calendar_id)
	assert anchored_out["calendar_name"] == "work calendar"
	assert "anchor" not in anchored_out
	assert anchorless_out["type"] == "calendar"
	assert anchorless_out["name"] == "work calendar"
	assert [source["source_type"] for source in _citable_sources(message)] == [
		"calendar_event",
		"calendar",
	]


@pytest.mark.asyncio
async def test_reminder_get_query_uses_container_search() -> None:
	"""the tool returns the anchored/anchorless container search union."""
	now = datetime.now(tz=UTC)
	app_context = _app_context()
	list_id = new_typeid("remlst")
	tool = ReminderGetTool()
	reminder_list = ReminderListModel(
		id=list_id,
		owner_id=app_context.principal.user.id,
		name="work",
		description="work reminders",
		color=None,
		icon=None,
		position=0.0,
		is_default=False,
		created_at=now,
		updated_at=now,
	)
	reminder_list.projects = []
	reminder = ReminderModel(
		id=new_typeid("rem"),
		owner_id=app_context.principal.user.id,
		list_id=list_id,
		title="send draft",
		description="draft notes",
		status=ReminderStatus.PENDING,
	)
	scored_hits = [
		ScoredResult(item=reminder, score=0.9),
		ScoredResult(item=reminder_list, score=0.8),
	]

	try:
		with (
			patch(
				"api.v1.service.chat.tools.reminders.search_reminder_lists",
				new=AsyncMock(return_value=scored_hits),
			) as search,
			patch(
				"api.v1.service.chat.tools.reminders.load_reminder_lists",
				new=AsyncMock(return_value={list_id: reminder_list}),
			),
			patch(
				"api.v1.service.chat.tools.reminders.get_list_counts",
				new=AsyncMock(
					return_value={
						"total_count": 2,
						"pending_count": 1,
						"completed_count": 1,
					}
				),
			),
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="draft",
				limit=5,
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "draft"
	assert search_await.kwargs["limit"] == 6
	assert search_await.kwargs["offset"] == 0
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["count"] == 2
	assert payload["next_offset"] is None
	anchored_out, anchorless_out = payload["results"]
	assert anchored_out["type"] == "reminder"
	assert anchored_out["id"] == str(reminder.id)
	assert anchored_out["title"] == "send draft"
	assert anchored_out["list_id"] == str(list_id)
	assert anchored_out["list_name"] == "work"
	assert anchored_out["status"] == ReminderStatus.PENDING.value
	assert "anchor" not in anchored_out
	assert anchorless_out["type"] == "reminder_list"
	assert anchorless_out["name"] == "work"
	assert anchorless_out["total_count"] == 2
	assert [source["source_type"] for source in _citable_sources(message)] == [
		"reminder",
		"reminder_list",
	]


@pytest.mark.asyncio
async def test_reminder_get_query_filters_completed() -> None:
	"""completed reminder anchors are dropped unless include_completed."""
	app_context = _app_context()
	completed = ReminderModel(
		id=new_typeid("rem"),
		owner_id=app_context.principal.user.id,
		list_id=new_typeid("remlst"),
		title="done thing",
		status=ReminderStatus.COMPLETED,
	)
	tool = ReminderGetTool()

	try:
		with (
			patch(
				"api.v1.service.chat.tools.reminders.search_reminder_lists",
				new=AsyncMock(return_value=[ScoredResult(item=completed, score=0.9)]),
			),
			patch(
				"api.v1.service.chat.tools.reminders.load_reminder_lists",
				new=AsyncMock(return_value={}),
			),
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="done",
				limit=5,
			)
	finally:
		await app_context.session.close()

	payload = json.loads(message.tool_output)
	assert payload["count"] == 0


@pytest.mark.asyncio
async def test_reminder_write_create_omits_list_id_for_default_list() -> None:
	now = datetime.now(tz=UTC)
	app_context = _app_context()
	list_id = new_typeid("remlst")
	created = Reminder(
		id=new_typeid("rem"),
		owner_id=app_context.principal.user.id,
		list_id=list_id,
		title="send draft",
		description=None,
		due_at=None,
		remind_at=None,
		recurrence=None,
		status=ReminderStatus.PENDING,
		parent_id=None,
		origin_message_id=None,
		position=0.0,
		completed_at=None,
		recurrence_until=None,
		series_origin_id=None,
		created_at=now,
		updated_at=now,
	)
	tool = ReminderWriteTool()

	try:
		with patch(
			"api.v1.service.chat.tools.reminders.create_reminder",
			new=AsyncMock(return_value=created),
		) as create_reminder:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				title="send draft",
			)
	finally:
		await app_context.session.close()

	create_reminder.assert_awaited_once()
	create_await = create_reminder.await_args
	assert create_await is not None
	data = create_await.args[0]
	assert data.title == "send draft"
	assert data.list_id is None
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["id"] == str(created.id)
	assert payload["list_id"] == str(list_id)


@pytest.mark.asyncio
async def test_calendar_write_create_omits_calendar_id_for_default_calendar() -> None:
	now = datetime.now(tz=UTC)
	app_context = _app_context()
	created = CalendarEvent(
		id=new_typeid("calev"),
		owner_id=app_context.principal.user.id,
		calendar_id=new_typeid("cal"),
		title="planning sync",
		description=None,
		start_at=now,
		end_at=now + timedelta(hours=1),
		all_day=False,
		timezone=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[],
		location=None,
		virtual_url=None,
		labels=[],
	)
	tool = CalendarEventWriteTool()

	try:
		with patch(
			"api.v1.service.chat.tools.calendar.create_calendar_event",
			new=AsyncMock(return_value=created),
		) as create_event:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				title="planning sync",
				start_at=now,
				end_at=now + timedelta(hours=1),
			)
	finally:
		await app_context.session.close()

	create_event.assert_awaited_once()
	create_await = create_event.await_args
	assert create_await is not None
	data = create_await.args[0]
	assert data.title == "planning sync"
	assert create_await.kwargs["calendar_id"] is None
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["event"]["id"] == str(created.id)
	assert payload["event"]["calendar_id"] == str(created.calendar_id)


@pytest.mark.asyncio
async def test_chat_get_query_uses_hybrid_search_and_chat_output_names() -> None:
	chat_id = new_typeid("thread")
	thread = SimpleNamespace(
		id=chat_id,
		title="planning chat",
		public_metadata={},
		messages=[],
	)
	message_id = new_typeid("msg")
	scored_threads = [
		ScoredResult(
			item=thread,
			score=0.9,
			hit=SearchHit(
				anchor=SearchResultAnchor(
					type=SearchResourceReferenceType.MESSAGE,
					id=message_id,
				),
				preview="planning details",
			),
		)
	]
	app_context = _app_context()
	tool = ChatGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.chats.search_threads",
			new=AsyncMock(return_value=scored_threads),
		) as search:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="planning",
				limit=3,
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "planning"
	assert search_await.kwargs["limit"] == 4
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["type"] == "message"
	assert payload["results"][0]["chat_id"] == str(chat_id)
	assert payload["results"][0]["message_id"] == str(message_id)
	assert payload["results"][0]["chat_title"] == "planning chat"
	assert payload["results"][0]["excerpt"] == "planning details"
	assert "id" not in payload["results"][0]
	assert "anchor" not in payload["results"][0]
	assert _citable_sources(message)[0]["source_type"] == "thread"


@pytest.mark.asyncio
async def test_chat_get_message_window_uses_before_and_after() -> None:
	now = datetime.now(tz=UTC)
	chat_id = new_typeid("thread")
	message_ids = [new_typeid("msg") for _ in range(5)]
	messages: list[Message] = [
		UserMessage(
			id=message_id,
			thread_id=chat_id,
			type=MessageType.USER,
			content=[{"type": "text", "text": f"message {index}"}],
			created_at=now + timedelta(minutes=index),
			updated_at=now + timedelta(minutes=index),
		)
		for index, message_id in enumerate(message_ids)
	]
	chat = SimpleNamespace(
		id=chat_id,
		title="planning chat",
		tags=[],
		is_temporary=False,
		owner_id=new_typeid("user"),
		current_message_id=message_ids[-1],
		projects=[],
		created_at=now,
		updated_at=now,
		last_activity_at=now,
		public_metadata={},
	)
	app_context = _app_context()
	tool = ChatGetTool()

	# anchor is at depth 2 (2 newer messages exist); before=1, after=2 spans
	# depths 0-3 = the 4 newest messages, leaving the oldest one out.
	branch_page = BranchPage(
		messages=messages[1:],
		total=len(messages),
		skip=0,
		siblings=[],
		sibling_counts=[],
	)

	try:
		with (
			patch(
				"api.v1.service.chat.tools.chats._load_message",
				new=AsyncMock(return_value=messages[2]),
			),
			patch(
				"api.v1.service.chat.tools.chats.get_thread",
				new=AsyncMock(return_value=chat),
			),
			patch(
				"api.v1.service.chat.tools.chats.get_branch_page",
				new=AsyncMock(return_value=branch_page),
			) as branch_page_mock,
			patch.object(
				tool,
				"_summary_payloads",
				new=AsyncMock(return_value=[]),
			),
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				message_id=str(message_ids[2]),
				before=1,
				after=2,
			)
	finally:
		await app_context.session.close()

	branch_page_mock.assert_awaited_once()
	page_await = branch_page_mock.await_args
	assert page_await is not None
	assert page_await.kwargs["anchor_message_id"] == message_ids[2]
	assert page_await.kwargs["before"] == 1
	assert page_await.kwargs["after"] == 2

	assert not message.is_error
	payload = json.loads(message.tool_output)
	page = payload["message_page"]
	assert [item["id"] for item in page["results"]] == [
		str(message_ids[1]),
		str(message_ids[2]),
		str(message_ids[3]),
		str(message_ids[4]),
	]
	assert page["has_more_older"] is True
	assert page["has_more_newer"] is False
	assert page["target_message_id"] == str(message_ids[2])
	assert _citable_sources(message)[0]["source_id"] == str(chat_id)


@pytest.mark.asyncio
async def test_resource_search_uses_hybrid_and_maps_chat_type() -> None:
	now = datetime.now(tz=UTC)
	chat_id = new_typeid("thread")
	file_id = new_typeid("file")
	app_context = _app_context()
	captured_query: str | None = None
	captured_types: list[SearchResultType] | None = None
	captured_limit: int | None = None
	captured_mode: SearchMode | None = None

	async def fake_search_stream(
		query: str,
		session: AsyncSession,
		*,
		principal: Principal,
		types: list[SearchResultType] | None,
		limit: int,
		search_params: SearchParams,
	) -> AsyncIterator[SearchResultItem]:
		nonlocal captured_limit, captured_mode, captured_query, captured_types
		_ = session, principal
		captured_query = query
		captured_types = types
		captured_limit = limit
		captured_mode = search_params.mode
		yield SearchResultItem(
			type=SearchResultType.THREAD,
			id=chat_id,
			title="planning chat",
			preview="notes",
			created_at=now,
			updated_at=now,
		)
		yield SearchResultItem(
			type=SearchResultType.FILE,
			id=file_id,
			title="brief.pdf",
			preview="draft",
			created_at=now,
			updated_at=now,
		)

	tool = ResourceSearchTool()

	try:
		with patch(
			"api.v1.service.chat.tools.resource_search.search_stream",
			new=fake_search_stream,
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="planning",
				types=["chat", "file"],
				limit=2,
			)
	finally:
		await app_context.session.close()

	assert captured_query == "planning"
	assert captured_types == [SearchResultType.THREAD, SearchResultType.FILE]
	assert captured_limit == 2
	assert captured_mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["count"] == 2
	assert payload["results"][0]["type"] == "chat"
	assert payload["results"][0]["chat_id"] == str(chat_id)
	assert "id" not in payload["results"][0]
	assert payload["results"][1]["type"] == "file"
	assert payload["results"][1]["id"] == str(file_id)
	assert [source["source_type"] for source in _citable_sources(message)] == [
		"thread",
		"file",
	]


def test_resource_search_schema_does_not_expose_private_resource_types() -> None:
	schema_text = json.dumps(ResourceSearchTool().parameters)

	assert '"prompt"' not in schema_text
	assert '"model"' not in schema_text


@pytest.mark.asyncio
async def test_note_get_query_uses_hybrid_search() -> None:
	app_context = _app_context()
	page = _scored_item(SearchResultType.NOTE, new_typeid("note"), "design notes")
	tool = NoteGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.notes.search_notes",
			new=AsyncMock(return_value=page),
		) as search:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="design",
				limit=4,
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "design"
	assert search_await.kwargs["limit"] == 5
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["title"] == "design notes"
	assert message.metadata is not None
	sources = message.metadata["_citable_sources"]
	assert isinstance(sources, list)
	first_source = sources[0]
	assert isinstance(first_source, dict)
	assert first_source["source_type"] == "note"


@pytest.mark.asyncio
async def test_project_get_query_uses_hybrid_search() -> None:
	app_context = _app_context()
	page = _scored_item(SearchResultType.PROJECT, new_typeid("proj"), "release")
	tool = ProjectGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.projects.search_projects",
			new=AsyncMock(return_value=page),
		) as search:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="release",
				limit=2,
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "release"
	assert search_await.kwargs["limit"] == 3
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["name"] == "release"
	assert _citable_sources(message)[0]["source_type"] == "project"


@pytest.mark.asyncio
async def test_file_get_query_uses_hybrid_search() -> None:
	app_context = _app_context()
	file_id = new_typeid("file")
	file_item = SimpleNamespace(
		id=file_id,
		filename="brief.pdf",
		mime_type="application/pdf",
		size_bytes=1024,
		description=None,
	)
	scored_files = [
		ScoredResult(item=file_item, score=0.9),
		*[ScoredResult(item=file_item, score=0.1) for _ in range(6)],
	]
	tool = FileGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.files.search_files",
			new=AsyncMock(return_value=scored_files),
		) as search:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="brief",
				limit=6,
				offset=0,
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "brief"
	assert search_await.kwargs["limit"] == 7
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["filename"] == "brief.pdf"
	assert _citable_sources(message)[0]["source_type"] == "file"


@pytest.mark.asyncio
async def test_file_get_batch_attaches_supported_media_to_one_message() -> None:
	app_context = _app_context()
	now = datetime.now(tz=UTC)
	img_id = new_typeid("file")
	doc_id = new_typeid("file")

	def _fake_file(file_id: TypeID, mime: str, name: str) -> MagicMock:
		f = MagicMock()
		f.id = file_id
		f.filename = name
		f.mime_type = mime
		f.size_bytes = 10
		f.created_at = now
		f.updated_at = now
		f.description = None
		f.status = MagicMock(value="ready")
		f.source = MagicMock(value="user_uploaded")
		return f

	files_by_id = {
		img_id: _fake_file(img_id, "image/png", "shot.png"),
		doc_id: _fake_file(doc_id, "application/pdf", "brief.pdf"),
	}

	async def _get_file(file_id: TypeID, *_a: object, **_k: object) -> MagicMock:
		return files_by_id[file_id]

	tool = FileGetTool()

	try:
		with (
			patch(
				"api.v1.service.chat.tools.files.get_file",
				new=AsyncMock(side_effect=_get_file),
			),
			patch(
				"api.v1.service.chat.tools.files.fetch_agent_input_modalities",
				new=AsyncMock(return_value={"text", "images"}),
			) as modalities,
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				file_ids=[str(img_id), str(doc_id)],
			)
	finally:
		await app_context.session.close()

	# all fetched media lands on one tool message sharing one protection turn
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["count"] == 2
	# only the image is a supported native modality -> one attachment
	assert len(message.attachments) == 1
	att = message.attachments[0]
	assert att.metadata is not None
	assert att.metadata["file_id"] == str(img_id)
	assert att.metadata["fetched"] is True
	assert att.metadata["updated_at"] == now.isoformat()
	# modalities are fetched once for the whole batch, not per file
	modalities.assert_awaited_once()


@pytest.mark.asyncio
async def test_file_get_batch_reports_missing_file_as_error_entry() -> None:
	app_context = _app_context()
	missing_id = new_typeid("file")

	async def _get_file(*_a: object, **_k: object) -> MagicMock:
		raise HTTPException(status_code=404, detail="file not found")

	tool = FileGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.files.get_file",
			new=AsyncMock(side_effect=_get_file),
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				file_ids=[str(missing_id)],
			)
	finally:
		await app_context.session.close()

	# a missing file does not fail the whole batch; it is reported per-entry
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["count"] == 1
	assert payload["results"][0]["status"] == "error"
	assert message.attachments == []


@pytest.mark.asyncio
async def test_file_get_query_with_single_file_searches_content() -> None:
	app_context = _app_context()
	file_id = new_typeid("file")
	hits = [
		FileContentChunkHit(
			text="beta line",
			score=0.91,
			chunk_index=0,
			chunk_count=2,
			line_start=2,
			line_end=3,
			char_start=11,
			char_end=20,
		)
	]
	tool = FileGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.files.query_file_content",
			new=AsyncMock(return_value=hits),
		) as query_content:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				file_ids=[str(file_id)],
				query="beta",
				limit=4,
			)
	finally:
		await app_context.session.close()

	query_content.assert_awaited_once()
	call = query_content.await_args
	assert call is not None
	assert call.kwargs["limit"] == 4
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["file_id"] == str(file_id)
	assert payload["results"][0]["text"] == "beta line"
	assert payload["results"][0]["line_start"] == 2
	assert payload["results"][0]["line_end"] == 3


@pytest.mark.asyncio
async def test_file_get_line_read_returns_text() -> None:
	app_context = _app_context()
	file_id = new_typeid("file")
	lines = FileContentLines(
		text="line two\nline three",
		line_start=2,
		line_end=3,
		total_lines=5,
	)
	tool = FileGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.files.read_file_content_lines",
			new=AsyncMock(return_value=lines),
		) as read_lines:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				file_ids=[str(file_id)],
				line_start=2,
				line_end=3,
			)
	finally:
		await app_context.session.close()

	read_lines.assert_awaited_once()
	call = read_lines.await_args
	assert call is not None
	assert call.kwargs["line_start"] == 2
	assert call.kwargs["line_end"] == 3
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["text"] == "line two\nline three"
	assert payload["total_lines"] == 5


@pytest.mark.asyncio
async def test_file_get_content_query_requires_single_file() -> None:
	app_context = _app_context()
	tool = FileGetTool()

	try:
		message = await tool.call(
			_state(),
			_agent_context(),
			_tool_call_context(),
			app_context,
			file_ids=[str(new_typeid("file")), str(new_typeid("file"))],
			query="beta",
		)
	finally:
		await app_context.session.close()

	assert message.is_error


@pytest.mark.asyncio
async def test_file_get_line_read_requires_single_file() -> None:
	app_context = _app_context()
	tool = FileGetTool()

	try:
		message = await tool.call(
			_state(),
			_agent_context(),
			_tool_call_context(),
			app_context,
			file_ids=[str(new_typeid("file")), str(new_typeid("file"))],
			line_start=1,
		)
	finally:
		await app_context.session.close()

	assert message.is_error


@pytest.mark.asyncio
async def test_file_get_batch_omits_media_when_include_media_false() -> None:
	app_context = _app_context()
	now = datetime.now(tz=UTC)
	img_id = new_typeid("file")

	def _media_file() -> MagicMock:
		f = MagicMock()
		f.id = img_id
		f.filename = "shot.png"
		f.mime_type = "image/png"
		f.size_bytes = 10
		f.created_at = now
		f.updated_at = now
		f.description = "a screenshot of a receipt"
		f.status = MagicMock(value="ready")
		f.source = MagicMock(value="user_uploaded")
		return f

	async def _get_file(*_a: object, **_k: object) -> MagicMock:
		return _media_file()

	tool = FileGetTool()

	try:
		with (
			patch(
				"api.v1.service.chat.tools.files.get_file",
				new=AsyncMock(side_effect=_get_file),
			),
			patch(
				"api.v1.service.chat.tools.files.fetch_agent_input_modalities",
				new=AsyncMock(return_value={"text", "images"}),
			) as modalities,
		):
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				file_ids=[str(img_id)],
				include_media=False,
			)
	finally:
		await app_context.session.close()

	assert not message.is_error
	# no media bytes attached and the modality lookup is skipped entirely.
	assert message.attachments == []
	modalities.assert_not_awaited()
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["description"] == "a screenshot of a receipt"


@pytest.mark.asyncio
async def test_memory_recall_uses_hybrid_search() -> None:
	app_context = _app_context()
	memory = SimpleNamespace(
		id=new_typeid("mem"), content="prefers focus", tags=["work"]
	)
	scored_memories = [ScoredResult(item=memory, score=0.9)]
	tool = MemoryRecallTool()

	try:
		with patch(
			"api.v1.service.chat.tools.memories.search_memories",
			new=AsyncMock(return_value=scored_memories),
		) as search:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="focus",
				limit=3,
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "focus"
	assert search_await.kwargs["limit"] == 4
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["content"] == "prefers focus"
