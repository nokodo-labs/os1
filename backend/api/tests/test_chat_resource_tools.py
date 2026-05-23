"""behavior tests for backend chat resource tools."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.calendar import CalendarEvent
from api.models.event import Event
from api.models.reminder import ReminderStatus
from api.models.user import User
from api.schemas.reminder import Reminder, ReminderListWithCounts
from api.schemas.scheduled_item import ScheduledItem
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service.auth import Principal
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
	user = User(
		id=new_typeid("user"),
		email="resource-tools@example.com",
		username="resource_tools_user",
		hashed_password="x",
		is_superuser=True,
	)
	return AppContext(
		session=AsyncSession(),
		principal=Principal(user=user, group_ids=(), permissions=frozenset()),
		event_emitter=_noop_event_emitter,
	)


def _search_page(
	result_type: SearchResultType,
	item_id: TypeID,
	title: str,
	preview: str = "preview",
) -> CursorPage:
	now = datetime.now(tz=UTC)
	return CursorPage(
		items=[
			SearchResultItem(
				type=result_type,
				id=item_id,
				title=title,
				preview=preview,
				created_at=now,
				updated_at=now,
			)
		]
	)


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
	assert payload["results"][0]["reminder_id"] == str(reminder_id)
	assert payload["results"][0]["status"] == ReminderStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_calendar_get_query_uses_hybrid_event_search() -> None:
	now = datetime.now(tz=UTC)
	page = CursorPage(
		items=[
			SearchResultItem(
				type=SearchResultType.CALENDAR_EVENT,
				id=new_typeid("calev"),
				title="planning sync",
				preview="agenda",
				created_at=now,
				updated_at=now,
			)
		],
		next_cursor="next",
		has_more=True,
	)
	app_context = _app_context()
	tool = CalendarEventGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.calendar.calendar_service.search_calendar_events",
			new=AsyncMock(return_value=page),
		) as search:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="planning",
				limit=7,
				cursor="cursor-1",
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "planning"
	assert search_await.kwargs["limit"] == 7
	assert search_await.kwargs["cursor"] == "cursor-1"
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["count"] == 1
	assert payload["has_more"] is True
	assert payload["next_cursor"] == "next"
	assert payload["results"][0]["title"] == "planning sync"


@pytest.mark.asyncio
async def test_reminder_get_query_searches_lists_and_reminders_with_hybrid() -> None:
	now = datetime.now(tz=UTC)
	app_context = _app_context()
	reminder_list = ReminderListWithCounts(
		id=new_typeid("remlst"),
		owner_id=TypeID(app_context.principal.user_id),
		name="work",
		description="work reminders",
		color=None,
		icon=None,
		position=0.0,
		is_default=False,
		project_ids=[],
		created_at=now,
		updated_at=now,
		total_count=2,
		pending_count=1,
		completed_count=1,
	)
	page = CursorPage(
		items=[
			SearchResultItem(
				type=SearchResultType.REMINDER,
				id=new_typeid("rem"),
				title="send draft",
				preview="draft notes",
				metadata={"status": ReminderStatus.PENDING.value},
				created_at=now,
				updated_at=now,
			)
		],
	)
	tool = ReminderGetTool()

	try:
		with (
			patch(
				"api.v1.service.chat.tools.reminders.reminder_service.search_reminder_lists",
				new=AsyncMock(return_value=[reminder_list]),
			) as list_search,
			patch(
				"api.v1.service.chat.tools.reminders.reminder_service.search_reminders",
				new=AsyncMock(return_value=page),
			) as reminder_search,
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

	list_search.assert_awaited_once()
	list_search_await = list_search.await_args
	assert list_search_await is not None
	assert list_search_await.args[0] == "draft"
	assert list_search_await.kwargs["limit"] == 5
	reminder_search.assert_awaited_once()
	reminder_search_await = reminder_search.await_args
	assert reminder_search_await is not None
	assert reminder_search_await.args[0] == "draft"
	assert reminder_search_await.kwargs["limit"] == 5
	assert reminder_search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["list_count"] == 1
	assert payload["reminder_count"] == 1
	assert payload["reminder_lists"][0]["total_count"] == 2
	assert payload["reminders"][0]["title"] == "send draft"


@pytest.mark.asyncio
async def test_reminder_write_create_omits_list_id_for_default_list() -> None:
	now = datetime.now(tz=UTC)
	app_context = _app_context()
	list_id = new_typeid("remlst")
	created = Reminder(
		id=new_typeid("rem"),
		owner_id=app_context.principal.user_id,
		list_id=list_id,
		title="send draft",
		description=None,
		due_at=None,
		remind_at=None,
		recurrence=None,
		status=ReminderStatus.PENDING,
		parent_id=None,
		source_thread_id=None,
		position=0.0,
		completed_at=None,
		recurrence_until=None,
		series_origin_id=None,
		metadata_={},
		created_at=now,
		updated_at=now,
	)
	tool = ReminderWriteTool()

	try:
		with patch(
			"api.v1.service.chat.tools.reminders.reminder_service.create_reminder",
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
		owner_id=app_context.principal.user_id,
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
			"api.v1.service.chat.tools.calendar.calendar_service.create_calendar_event",
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
	now = datetime.now(tz=UTC)
	chat_id = new_typeid("thread")
	page = CursorPage(
		items=[
			SearchResultItem(
				type=SearchResultType.THREAD,
				id=chat_id,
				title="planning chat",
				preview="notes",
				created_at=now,
				updated_at=now,
			)
		]
	)
	app_context = _app_context()
	tool = ChatGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.chats.chat_service.search_threads",
			new=AsyncMock(return_value=page),
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
	assert search_await.kwargs["limit"] == 3
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["type"] == "chat"
	assert payload["results"][0]["chat_id"] == str(chat_id)
	assert "id" not in payload["results"][0]


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
			"api.v1.service.chat.tools.resource_search.search_service.search_stream",
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


def test_resource_search_schema_does_not_expose_private_resource_types() -> None:
	schema_text = json.dumps(ResourceSearchTool().parameters)

	assert '"prompt"' not in schema_text
	assert '"model"' not in schema_text


@pytest.mark.asyncio
async def test_note_get_query_uses_hybrid_search() -> None:
	app_context = _app_context()
	page = _search_page(SearchResultType.NOTE, new_typeid("note"), "design notes")
	tool = NoteGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.notes.note_service.search_notes",
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
	assert search_await.kwargs["limit"] == 4
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
	page = _search_page(SearchResultType.PROJECT, new_typeid("proj"), "release")
	tool = ProjectGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.projects.project_service.search_projects",
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
	assert search_await.kwargs["limit"] == 2
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["name"] == "release"


@pytest.mark.asyncio
async def test_file_get_query_uses_hybrid_search() -> None:
	app_context = _app_context()
	now = datetime.now(tz=UTC)
	page = CursorPage(
		items=[
			SearchResultItem(
				type=SearchResultType.FILE,
				id=new_typeid("file"),
				title="brief.pdf",
				preview="draft",
				created_at=now,
				updated_at=now,
			)
		],
		next_cursor="next",
		has_more=True,
	)
	tool = FileGetTool()

	try:
		with patch(
			"api.v1.service.chat.tools.files.file_service.search_files",
			new=AsyncMock(return_value=page),
		) as search:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				query="brief",
				limit=6,
				cursor="cursor-1",
			)
	finally:
		await app_context.session.close()

	search.assert_awaited_once()
	search_await = search.await_args
	assert search_await is not None
	assert search_await.args[0] == "brief"
	assert search_await.kwargs["limit"] == 6
	assert search_await.kwargs["cursor"] == "cursor-1"
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["has_more"] is True
	assert payload["next_cursor"] == "next"
	assert payload["results"][0]["title"] == "brief.pdf"


@pytest.mark.asyncio
async def test_memory_recall_uses_hybrid_search() -> None:
	app_context = _app_context()
	page = _search_page(SearchResultType.MEMORY, new_typeid("mem"), "prefers focus")
	tool = MemoryRecallTool()

	try:
		with patch(
			"api.v1.service.chat.tools.memories.memory_service.search_memories",
			new=AsyncMock(return_value=page),
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
	assert search_await.kwargs["limit"] == 3
	assert search_await.kwargs["search_params"].mode == SearchMode.HYBRID
	assert not message.is_error
	payload = json.loads(message.tool_output)
	assert payload["results"][0]["title"] == "prefers focus"
