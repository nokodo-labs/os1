"""regression tests for send_notification tool authorization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.tests.factories import make_principal
from api.v1.service.authentication import Principal
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.tools import send_notification as send_notification_module
from api.v1.service.chat.tools.send_notification import SendNotificationTool
from nokodo_ai import AgentContext, AgentIterationSnapshot, AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.threads import Thread
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _state() -> AgentIterationSnapshot[AppContext]:
	return AgentIterationState[AppContext](thread=Thread(), tools=[]).snapshot()


def _agent_context() -> AgentContext:
	return AgentContext(model=ChatModel.model_construct(model_name="stub"))


def _tool_call_context() -> ToolCallContext:
	return ToolCallContext(tool_call_id="tool-call", tool_call_start_time=0.0)


def _make_principal(is_superuser: bool = False) -> Principal:
	return make_principal(is_superuser=is_superuser)


def _mock_session_factory(session: AsyncSession) -> MagicMock:
	"""return a context manager mock that yields session from async_session_local."""
	ctx = MagicMock()
	ctx.__aenter__ = AsyncMock(return_value=session)
	ctx.__aexit__ = AsyncMock(return_value=False)
	return ctx


@pytest.mark.asyncio
async def test_send_notification_rejects_cross_user_target_without_thread(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""non-admin agent cannot target a user_id when there is no thread context
	(e.g. ephemeral run).
	"""
	principal = _make_principal(is_superuser=False)
	victim_id = str(new_typeid("user"))
	tool_session = MagicMock(spec=AsyncSession)
	emitted_events: list[object] = []
	create_calls: list[list[TypeID]] = []

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	async def fake_create_notifications(
		_session: AsyncSession,
		*,
		payload: object,
		user_ids: list[TypeID],
		event_type: str,
		agent_id: TypeID | None = None,
	) -> list[object]:
		create_calls.append(list(user_ids))
		return []

	monkeypatch.setattr(
		send_notification_module,
		"async_session_local",
		lambda: _mock_session_factory(tool_session),
	)
	monkeypatch.setattr(
		send_notification_module,
		"create_notifications",
		fake_create_notifications,
	)

	app_ctx = AppContext(
		session=MagicMock(spec=AsyncSession),
		principal=principal,
		event_emitter=capture_event,
		agent_id=new_typeid("agent"),
		thread_id=None,
	)
	result = await SendNotificationTool().call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="POC notification",
		body="benign proof-of-concept body",
		user_id=victim_id,
	)

	assert isinstance(result, ToolMessage)
	assert result.is_error is True
	assert "forbidden" in str(result.tool_output).lower()
	assert create_calls == []
	assert emitted_events == []


@pytest.mark.asyncio
async def test_send_notification_rejects_non_participant_target(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""non-admin agent cannot target a user_id absent from the thread's
	accessible set.
	"""
	principal = _make_principal(is_superuser=False)
	outsider_id = new_typeid("user")
	thread_id = new_typeid("thread")
	tool_session = MagicMock(spec=AsyncSession)
	emitted_events: list[object] = []
	create_calls: list[list[TypeID]] = []

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	async def fake_list_accessible_user_ids(
		resource_refs: object,
		session: AsyncSession,
		**_kwargs: object,
	) -> list[TypeID]:
		return [principal.user.id]

	async def fake_create_notifications(
		_session: AsyncSession,
		*,
		payload: object,
		user_ids: list[TypeID],
		event_type: str,
		agent_id: TypeID | None = None,
	) -> list[object]:
		create_calls.append(list(user_ids))
		return []

	monkeypatch.setattr(
		send_notification_module,
		"async_session_local",
		lambda: _mock_session_factory(tool_session),
	)
	monkeypatch.setattr(
		send_notification_module,
		"list_resource_access_user_ids_for_resources",
		fake_list_accessible_user_ids,
	)
	monkeypatch.setattr(
		send_notification_module,
		"create_notifications",
		fake_create_notifications,
	)

	app_ctx = AppContext(
		session=MagicMock(spec=AsyncSession),
		principal=principal,
		event_emitter=capture_event,
		agent_id=new_typeid("agent"),
		thread_id=thread_id,
	)
	result = await SendNotificationTool().call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="POC notification",
		body="benign proof-of-concept body",
		user_id=str(outsider_id),
	)

	assert isinstance(result, ToolMessage)
	assert result.is_error is True
	assert "forbidden" in str(result.tool_output).lower()
	assert create_calls == []
	assert emitted_events == []


@pytest.mark.asyncio
async def test_send_notification_target_is_thread_scoped_for_a_superuser_run(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""who started the run does not widen the recipient set.

	the arguments are model-generated and the model reads untrusted text, so an
	operator-started run must not be able to notify arbitrary users.
	"""
	principal = _make_principal(is_superuser=True)
	outsider_id = new_typeid("user")
	thread_id = new_typeid("thread")
	tool_session = MagicMock(spec=AsyncSession)
	emitted_events: list[object] = []
	create_calls: list[list[TypeID]] = []

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	async def fake_list_accessible_user_ids(
		resource_refs: object,
		session: AsyncSession,
		**_kwargs: object,
	) -> list[TypeID]:
		return [principal.user.id]

	async def fake_create_notifications(
		_session: AsyncSession,
		*,
		payload: object,
		user_ids: list[TypeID],
		event_type: str,
		agent_id: TypeID | None = None,
	) -> list[object]:
		create_calls.append(list(user_ids))
		return []

	monkeypatch.setattr(
		send_notification_module,
		"async_session_local",
		lambda: _mock_session_factory(tool_session),
	)
	monkeypatch.setattr(
		send_notification_module,
		"list_resource_access_user_ids_for_resources",
		fake_list_accessible_user_ids,
	)
	monkeypatch.setattr(
		send_notification_module,
		"create_notifications",
		fake_create_notifications,
	)

	app_ctx = AppContext(
		session=MagicMock(spec=AsyncSession),
		principal=principal,
		event_emitter=capture_event,
		agent_id=new_typeid("agent"),
		thread_id=thread_id,
	)
	result = await SendNotificationTool().call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="POC notification",
		body="benign proof-of-concept body",
		user_id=str(outsider_id),
	)

	assert isinstance(result, ToolMessage)
	assert result.is_error is True
	assert "forbidden" in str(result.tool_output).lower()
	assert create_calls == []
	assert emitted_events == []


@pytest.mark.asyncio
async def test_send_notification_allows_thread_participant_target(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Non-admin agent can target a user_id that is a thread participant."""
	principal = _make_principal(is_superuser=False)
	recipient_id = new_typeid("user")
	thread_id = new_typeid("thread")
	tool_session = MagicMock(spec=AsyncSession)
	emitted_events: list[object] = []
	create_calls: list[list[TypeID]] = []

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	async def fake_list_accessible_user_ids(
		resource_refs: object,
		session: AsyncSession,
		**_kwargs: object,
	) -> list[TypeID]:
		return [recipient_id]

	async def fake_create_notifications(
		_session: AsyncSession,
		*,
		payload: object,
		user_ids: list[TypeID],
		event_type: str,
		agent_id: TypeID | None = None,
	) -> list[object]:
		create_calls.append(list(user_ids))
		return [MagicMock(id=new_typeid("notif"))]

	monkeypatch.setattr(
		send_notification_module,
		"async_session_local",
		lambda: _mock_session_factory(tool_session),
	)
	monkeypatch.setattr(
		send_notification_module,
		"list_resource_access_user_ids_for_resources",
		fake_list_accessible_user_ids,
	)
	monkeypatch.setattr(
		send_notification_module,
		"create_notifications",
		fake_create_notifications,
	)

	app_ctx = AppContext(
		session=MagicMock(spec=AsyncSession),
		principal=principal,
		event_emitter=capture_event,
		agent_id=new_typeid("agent"),
		thread_id=thread_id,
	)
	result = await SendNotificationTool().call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="Hello",
		body="you are a thread participant",
		user_id=str(recipient_id),
	)

	first_event = emitted_events[0] if emitted_events else None
	first_event_data = getattr(first_event, "data", {}) if first_event else {}

	assert isinstance(result, ToolMessage)
	assert result.is_error is False
	assert len(create_calls) == 1
	assert create_calls[0] == [recipient_id]
	assert first_event_data.get("target_user_id") == str(recipient_id)


@pytest.mark.asyncio
async def test_send_notification_does_not_emit_sent_event_when_creation_fails(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = _make_principal()
	tool_session = MagicMock(spec=AsyncSession)
	emitted_events: list[object] = []

	async def recipients(*_args: object, **_kwargs: object) -> list[TypeID]:
		return [principal.user.id]

	async def fail(*_args: object, **_kwargs: object) -> list[object]:
		raise RuntimeError("notification write failed")

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	monkeypatch.setattr(
		send_notification_module,
		"async_session_local",
		lambda: _mock_session_factory(tool_session),
	)
	monkeypatch.setattr(
		send_notification_module,
		"list_resource_access_user_ids_for_resources",
		recipients,
	)
	monkeypatch.setattr(send_notification_module, "create_notifications", fail)
	app_ctx = AppContext(
		session=MagicMock(spec=AsyncSession),
		principal=principal,
		event_emitter=capture_event,
		agent_id=new_typeid("agent"),
		thread_id=new_typeid("thread"),
	)

	result = await SendNotificationTool().call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="Hello",
	)

	assert result.is_error is True
	assert emitted_events == []


@pytest.mark.asyncio
async def test_send_notification_rejects_empty_recipient_set(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = _make_principal()
	tool_session = MagicMock(spec=AsyncSession)
	emitted_events: list[object] = []

	async def no_recipients(*_args: object, **_kwargs: object) -> list[TypeID]:
		return []

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	monkeypatch.setattr(
		send_notification_module,
		"async_session_local",
		lambda: _mock_session_factory(tool_session),
	)
	monkeypatch.setattr(
		send_notification_module,
		"list_resource_access_user_ids_for_resources",
		no_recipients,
	)
	app_ctx = AppContext(
		session=MagicMock(spec=AsyncSession),
		principal=principal,
		event_emitter=capture_event,
		agent_id=new_typeid("agent"),
		thread_id=new_typeid("thread"),
	)

	result = await SendNotificationTool().call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="Hello",
	)

	assert result.is_error is True
	assert "no recipients" in result.tool_output
	assert emitted_events == []
