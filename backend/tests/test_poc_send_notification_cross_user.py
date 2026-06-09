"""regression tests for send_notification authorization."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
	sys.path.insert(0, str(BACKEND_ROOT))

from api.boot_settings import boot_settings

boot_settings.TESTING = True

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.tools import send_notification as send_notification_module
from api.v1.service.chat.tools.send_notification import SendNotificationTool
from nokodo_ai import AgentContext, AgentIterationSnapshot, AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.threads import Thread


class _FakeSession:
	def __init__(self) -> None:
		self.committed = False

	async def commit(self) -> None:
		self.committed = True


class _FakeAsyncSessionContext:
	def __init__(self, session: _FakeSession) -> None:
		self._session = session

	async def __aenter__(self) -> _FakeSession:
		return self._session

	async def __aexit__(self, exc_type, exc, tb) -> bool:
		_ = exc_type, exc, tb
		return False


def _state() -> AgentIterationSnapshot[AppContext]:
	return AgentIterationState[AppContext](thread=Thread(), tools=[]).snapshot()


def _agent_context() -> AgentContext:
	return AgentContext(model=ChatModel.model_construct(model_name="stub"))


def _tool_call_context() -> ToolCallContext:
	return ToolCallContext(tool_call_id="tool-call", tool_call_start_time=0.0)


@pytest.mark.asyncio
async def test_send_notification_rejects_cross_user_target_without_thread() -> None:
	"""A non-admin agent cannot target an arbitrary victim user_id."""
	suffix = uuid4().hex[:8]
	attacker = SimpleNamespace(id=f"user_attacker_{suffix}", is_superuser=False)
	victim = SimpleNamespace(id=f"user_victim_{suffix}", is_superuser=False)
	attacker_principal = SimpleNamespace(
		user=attacker,
		user_id=attacker.id,
		is_admin=False,
	)
	emitted_events: list[object] = []
	create_calls: list[dict[str, object]] = []

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	async def fake_create_notifications(
		_session: object,
		*,
		payload: object,
		user_ids: list[object],
		event_type: str,
		agent_id: object | None = None,
	) -> list[SimpleNamespace]:
		create_calls.append(
			{
				"payload": payload,
				"user_ids": list(user_ids),
				"event_type": event_type,
				"agent_id": agent_id,
			}
		)
		return [SimpleNamespace(id=f"notif_{suffix}")]

	fake_session = _FakeSession()
	send_notification_module.async_session_local = lambda: _FakeAsyncSessionContext(
		fake_session
	)
	send_notification_module.notification_service.create_notifications = (
		fake_create_notifications
	)

	app_ctx = AppContext(
		session=fake_session,  # type: ignore[arg-type]
		principal=attacker_principal,
		event_emitter=capture_event,
		agent_id=SimpleNamespace(id="agent_poc"),
		thread_id=None,
	)
	tool = SendNotificationTool()
	result = await tool.call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="POC notification",
		body="benign proof-of-concept message",
		user_id=str(victim.id),
	)

	assert isinstance(result, ToolMessage)
	assert result.is_error is True
	assert "forbidden" in str(result.tool_output).lower()
	assert fake_session.committed is False
	assert create_calls == []
	assert emitted_events == []


@pytest.mark.asyncio
async def test_send_notification_allows_accessible_thread_user() -> None:
	"""A non-admin agent can target a user who is accessible in the thread."""
	suffix = uuid4().hex[:8]
	attacker = SimpleNamespace(id=f"user_attacker_{suffix}", is_superuser=False)
	victim = SimpleNamespace(id=f"user_victim_{suffix}", is_superuser=False)
	attacker_principal = SimpleNamespace(
		user=attacker,
		user_id=attacker.id,
		is_admin=False,
	)
	emitted_events: list[object] = []
	create_calls: list[dict[str, object]] = []

	async def capture_event(event: object) -> None:
		emitted_events.append(event)

	async def fake_list_accessible_user_ids(*_args: object, **_kwargs: object) -> list[str]:
		return [victim.id]

	async def fake_create_notifications(
		_session: object,
		*,
		payload: object,
		user_ids: list[object],
		event_type: str,
		agent_id: object | None = None,
	) -> list[SimpleNamespace]:
		create_calls.append(
			{
				"payload": payload,
				"user_ids": list(user_ids),
				"event_type": event_type,
				"agent_id": agent_id,
			}
		)
		return [SimpleNamespace(id=f"notif_{suffix}")]

	fake_session = _FakeSession()
	send_notification_module.async_session_local = lambda: _FakeAsyncSessionContext(
		fake_session
	)
	send_notification_module.list_accessible_user_ids = fake_list_accessible_user_ids
	send_notification_module.notification_service.create_notifications = (
		fake_create_notifications
	)

	app_ctx = AppContext(
		session=fake_session,  # type: ignore[arg-type]
		principal=attacker_principal,
		event_emitter=capture_event,
		agent_id=SimpleNamespace(id="agent_poc"),
		thread_id="thread_poc",
	)
	result = await SendNotificationTool().call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		app_ctx,
		title="POC notification",
		body="benign proof-of-concept message",
		user_id=str(victim.id),
	)

	first_event = emitted_events[0] if emitted_events else None
	first_event_data = getattr(first_event, "data", {}) if first_event else {}

	assert isinstance(result, ToolMessage)
	assert result.is_error is False
	assert fake_session.committed is True
	assert len(create_calls) == 1
	assert create_calls[0]["user_ids"] == [victim.id]
	assert first_event_data["target_user_id"] == str(victim.id)
