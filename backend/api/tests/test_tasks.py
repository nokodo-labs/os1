import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TypedDict

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq.brokers.inmemory_broker import InMemoryBroker
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask

from api.boot_settings import boot_settings
from api.models.access_rule import AccessLevel
from api.models.message import AssistantMessage, Message, MessageType, UserMessage
from api.models.task import Task, TaskStatus, TaskType
from api.models.thread import Thread
from api.models.thread_summary import SummaryPurpose
from api.permissions import MentionableSubjectType, ResourceType
from api.schemas.agent import AgentConfig, AgentCreate
from api.schemas.message import (
	BranchLeaf,
	Citation,
	CitationSource,
	ImageContent,
	MessageCreate,
	MessageMention,
	MessageSplice,
	RunBlockRef,
	TextContent,
)
from api.schemas.task import TaskCreate, TaskListFilters, TaskUpdate
from api.schemas.user import UserCreate
from api.settings import settings
from api.taskiq import broker
from api.v1.service import access_rules
from api.v1.service import agents as agent_service
from api.v1.service import tasks as task_service
from api.v1.service import users as user_service
from api.v1.service.authentication import Principal
from api.v1.service.chat import thread_maintenance as thread_maintenance_service
from api.v1.service.chat.thread_maintenance import (
	THREAD_INACTIVITY_DISPATCH_TASK,
	THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID,
	THREAD_MAINTENANCE_BACKFILL_TASK,
	THREAD_MAINTENANCE_TASK,
	clear_disabled_thread_maintenance_backfill_schedule,
	fail_stale_thread_related_tasks,
	run_thread_maintenance_backfill_sweep,
	schedule_thread_inactivity_maintenance,
	start_thread_maintenance_task,
)
from api.v1.service.runs import execution as run_execution
from api.v1.service.runs.contracts import PersistedRunInput
from api.v1.service.runs.launch import _capture_run_input
from api.v1.service.threads import MessageDraft, create_message
from api.v1.service.threads import summaries as summary_service
from api.v1.tasks.threads import run_thread_maintenance_task
from nokodo_ai.adapters.chat import GenerationBadRequestError
from nokodo_ai.deltas import AgentDelta, ChatModelDelta
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID, new_typeid


class _TaskAuth(TypedDict):
	user_id: str
	headers: dict[str, str]


class _FakeThreadScheduleSource:
	def __init__(self) -> None:
		self.deleted: list[str] = []
		self.scheduled: list[tuple[str, datetime, str, str]] = []

	async def delete_schedule(self, schedule_id: str) -> None:
		self.deleted.append(schedule_id)

	async def add_schedule(self, schedule: ScheduledTask) -> None:
		if (
			schedule.task_name != THREAD_INACTIVITY_DISPATCH_TASK
			or schedule.time is None
			or len(schedule.args) != 2
		):
			raise AssertionError("unexpected thread maintenance dispatch")
		thread_id, observed_last_activity_at = schedule.args
		self.scheduled.append(
			(
				schedule.schedule_id,
				schedule.time,
				str(thread_id),
				str(observed_last_activity_at),
			)
		)


def _task_auth(user_auth: dict[str, object]) -> _TaskAuth:
	user = user_auth.get("user")
	headers = user_auth.get("headers")
	if not isinstance(user, dict) or not isinstance(headers, dict):
		raise AssertionError("user_auth fixture has an unexpected shape")
	match user:
		case {"id": str(user_id)}:
			pass
		case _:
			raise AssertionError("user_auth fixture is missing a user id")
	typed_headers: dict[str, str] = {}
	for key, value in headers.items():
		if not isinstance(key, str) or not isinstance(value, str):
			raise AssertionError("user_auth headers must be strings")
		typed_headers[key] = value
	return {"user_id": user_id, "headers": typed_headers}


class _FakeCompletedRunAgent:
	async def run(
		self,
		*_args: object,
		**_kwargs: object,
	) -> AsyncIterator[AgentDelta]:
		async def stream() -> AsyncIterator[AgentDelta]:
			yield AgentDelta(
				chat=ChatModelDelta(
					message=SDKAssistantMessage.from_text(
						"hello from the agent"
					).model_copy(update={"finish_reason": "stop"}),
					done=True,
				),
				chunk_index=0,
			)
			yield AgentDelta.done_sentinel(chunk_index=1)

		return stream()


class _FakeMultiDeltaRunAgent:
	async def run(
		self,
		*_args: object,
		**_kwargs: object,
	) -> AsyncIterator[AgentDelta]:
		async def stream() -> AsyncIterator[AgentDelta]:
			yield AgentDelta(
				chat=ChatModelDelta(
					message=SDKAssistantMessage.from_text("hello "),
				),
				chunk_index=0,
			)
			yield AgentDelta(
				chat=ChatModelDelta(
					message=SDKAssistantMessage.from_text("from the agent").model_copy(
						update={"finish_reason": "stop"}
					),
					done=True,
				),
				chunk_index=1,
			)
			yield AgentDelta.done_sentinel(chunk_index=2)

		return stream()


class _FakeBadRequestRunAgent:
	async def run(
		self,
		*_args: object,
		**_kwargs: object,
	) -> AsyncIterator[AgentDelta]:
		async def stream() -> AsyncIterator[AgentDelta]:
			raise GenerationBadRequestError(
				"maximum context length exceeded",
				provider="openai.chat_completions",
				status_code=400,
				code="context_length_exceeded",
			)
			yield AgentDelta.done_sentinel(chunk_index=0)

		return stream()


class _FakePartialBadRequestRunAgent:
	async def run(
		self,
		*_args: object,
		**_kwargs: object,
	) -> AsyncIterator[AgentDelta]:
		async def stream() -> AsyncIterator[AgentDelta]:
			yield AgentDelta(
				chat=ChatModelDelta(
					message=SDKAssistantMessage.from_text("partial answer"),
					done=False,
				),
				chunk_index=0,
			)
			raise GenerationBadRequestError(
				"maximum context length exceeded",
				provider="openai.chat_completions",
				status_code=400,
				code="context_length_exceeded",
			)
			yield AgentDelta.done_sentinel(chunk_index=1)

		return stream()


class _FakeCompletedThenPartialBadRequestRunAgent:
	async def run(
		self,
		*_args: object,
		**_kwargs: object,
	) -> AsyncIterator[AgentDelta]:
		async def stream() -> AsyncIterator[AgentDelta]:
			yield AgentDelta(
				chat=ChatModelDelta(
					message=SDKAssistantMessage.from_text(
						"complete replacement"
					).model_copy(update={"finish_reason": "stop"}),
					done=True,
				),
				chunk_index=0,
			)
			yield AgentDelta(
				chat=ChatModelDelta(
					message=SDKAssistantMessage.from_text("partial continuation"),
					done=False,
				),
				chunk_index=1,
			)
			raise GenerationBadRequestError(
				"maximum context length exceeded",
				provider="openai.chat_completions",
				status_code=400,
				code="context_length_exceeded",
			)
			yield AgentDelta.done_sentinel(chunk_index=2)

		return stream()


async def _create_thread_with_current_message(
	db_session: AsyncSession,
	user_id: TypeID,
	last_activity_at: datetime,
	title: str | None = None,
	tags: list[str] | None = None,
) -> Thread:
	thread_id = TypeID(new_typeid("thread"))
	message_id = TypeID(new_typeid("msg"))
	thread = Thread(
		id=thread_id,
		owner_id=user_id,
		title=title,
		tags=[] if tags is None else tags,
		last_activity_at=last_activity_at,
	)
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		UserMessage(
			id=message_id,
			thread_id=thread_id,
			type=MessageType.USER,
			content=[{"type": "text", "text": "hello"}],
		)
	)
	await db_session.flush()
	thread.current_message_id = message_id
	await db_session.flush()
	await db_session.execute(
		update(Thread)
		.where(Thread.id == thread_id)
		.values(last_activity_at=last_activity_at)
	)
	await db_session.flush()
	await db_session.refresh(thread)
	return thread


async def _persist_run_input(
	db_session: AsyncSession,
	thread_id: TypeID,
	message_input: MessageCreate,
	principal: Principal,
	splice: MessageSplice | None = None,
) -> PersistedRunInput:
	"""write a run's input the way the launcher does, and capture it."""
	draft = MessageDraft.from_request(message_input)
	if splice is not None:
		draft.splice = splice
	written = await create_message(
		thread_id,
		draft,
		db_session,
		principal=principal,
	)
	return _capture_run_input(written)


@pytest.mark.asyncio
async def test_create_task(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test creating a task."""
	auth = _task_auth(user_auth)
	headers = auth["headers"]
	user_id = auth["user_id"]
	payload = {
		"user_id": user_id,
		"task_type": "custom",
		"stage": "initialization",
	}
	response = await client.post("/v1/tasks", json=payload, headers=headers)
	assert response.status_code == 201
	data = response.json()
	assert data["user_id"] == user_id
	assert data["task_type"] == "custom"
	assert data["status"] == "running"
	assert "id" in data


@pytest.mark.asyncio
async def test_list_tasks(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test listing tasks."""
	auth = _task_auth(user_auth)
	headers = auth["headers"]
	user_id = auth["user_id"]
	# Create a task first
	payload = {
		"user_id": user_id,
		"task_type": "custom",
	}
	await client.post("/v1/tasks", json=payload, headers=headers)

	response = await client.get("/v1/tasks", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert len(data) >= 1
	assert data[0]["user_id"] == user_id


@pytest.mark.asyncio
async def test_list_tasks_sorting(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""List tasks supports server-side sort_by + sort_dir."""
	auth = _task_auth(user_auth)
	headers = auth["headers"]
	user_id = auth["user_id"]

	resp_b = await client.post(
		"/v1/tasks",
		headers=headers,
		json={
			"user_id": user_id,
			"task_type": "custom",
			"stage": "b",
		},
	)
	assert resp_b.status_code == 201
	resp_a = await client.post(
		"/v1/tasks",
		headers=headers,
		json={
			"user_id": user_id,
			"task_type": "custom",
			"stage": "a",
		},
	)
	assert resp_a.status_code == 201

	response = await client.get(
		"/v1/tasks",
		headers=headers,
		params={"sort_by": "stage", "sort_dir": "asc", "limit": 50},
	)
	assert response.status_code == 200
	data = response.json()
	assert [t["stage"] for t in data[:2]] == ["a", "b"]


@pytest.mark.asyncio
async def test_list_tasks_filter(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test listing tasks with filters."""
	auth = _task_auth(user_auth)
	headers = auth["headers"]
	user_id = auth["user_id"]
	# Create tasks with different statuses
	task1 = {
		"user_id": user_id,
		"task_type": "custom",
	}
	task2 = {
		"user_id": user_id,
		"task_type": "custom",
	}
	await client.post("/v1/tasks", json=task1, headers=headers)
	created_completed = await client.post("/v1/tasks", json=task2, headers=headers)
	await client.patch(
		f"/v1/tasks/{created_completed.json()['id']}",
		json={"status": "complete"},
		headers=headers,
	)

	# Filter by status
	response = await client.get(
		"/v1/tasks",
		params={"status_filter": "running"},
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert all(t["status"] == "running" for t in data)

	# Filter by owner_id
	response = await client.get(
		"/v1/tasks",
		params={"owner_id": user_id},
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert all(t["user_id"] == user_id for t in data)


@pytest.mark.asyncio
async def test_update_task(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test updating a task."""
	auth = _task_auth(user_auth)
	headers = auth["headers"]
	user_id = auth["user_id"]
	# Create a task
	payload = {
		"user_id": user_id,
		"task_type": "custom",
	}
	create_res = await client.post("/v1/tasks", json=payload, headers=headers)
	task_id = create_res.json()["id"]

	# Update the task
	update_payload = {"status": "running", "progress": 50}
	response = await client.patch(
		f"/v1/tasks/{task_id}",
		json=update_payload,
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert data["status"] == "running"
	assert data["progress"] == 50


@pytest.mark.asyncio
async def test_update_task_not_found(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test updating a non-existent task."""
	headers = _task_auth(user_auth)["headers"]
	response = await client.patch(
		f"/v1/tasks/{new_typeid('task')}",
		json={"status": "complete"},
		headers=headers,
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_service_create_task(db_session: AsyncSession) -> None:
	"""Test creating a task directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_service@example.com",
		username="task_service",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		stage="init",
	)
	task = await task_service.create_task(task_in, db_session, principal=principal)
	assert task.user_id == user.id
	assert task.status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_start_task_executes_registered_runner_through_taskiq(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""starting a named task enqueues and runs its registered TaskIQ runner."""
	user = await user_service.create_user(
		UserCreate(
			email="taskiq_start@example.com",
			username="taskiq_start",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	runner_name = "tests.taskiq.execution"
	original_runners = dict(task_service._task_runners)
	in_memory_broker = InMemoryBroker(await_inplace=True)
	in_memory_entrypoint = in_memory_broker.task(
		task_name=task_service.execute_started_task_entrypoint.task_name
	)(task_service.execute_started_task_entrypoint.original_func)
	monkeypatch.setattr(
		task_service, "execute_started_task_entrypoint", in_memory_entrypoint
	)

	@task_service.register_task_runner(runner_name)
	async def _runner(ctx: task_service.TaskContext) -> JSONObject:
		await ctx.update(progress=55, stage="worked")
		return {"ok": True, "runtime": ctx.runtime.get("value")}

	await in_memory_broker.startup()
	try:
		task = await task_service.start_task(
			db_session,
			principal=principal,
			task_type=TaskType.CUSTOM,
			task_name=runner_name,
			runtime={"value": "from taskiq"},
		)
		await db_session.refresh(task)
		assert task.status == TaskStatus.COMPLETED
		assert task.progress == 100
		assert task.result == {"ok": True, "runtime": "from taskiq"}
	finally:
		await in_memory_broker.shutdown()
		task_service._task_runners.clear()
		task_service._task_runners.update(original_runners)


@pytest.mark.asyncio
async def test_start_thread_maintenance_task_reuses_fresh_active_task(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""fresh active maintenance tasks are reused instead of duplicated."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_maintenance_fresh@example.com",
			username="thread_maintenance_fresh",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread_id = TypeID(new_typeid("thread"))
	thread = Thread(id=thread_id, owner_id=user.id, tags=[])
	db_session.add(thread)
	await db_session.flush()
	active_task = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="starting maintenance",
		started_at=datetime.now(tz=UTC),
		last_event_at=datetime.now(tz=UTC),
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: THREAD_MAINTENANCE_TASK,
			"thread_id": str(thread_id),
			"replace_metadata": False,
		},
	)
	db_session.add(active_task)
	await db_session.commit()
	await db_session.refresh(active_task)

	enqueued_task_ids: list[str] = []

	async def fake_enqueue_started_task(
		task_id: TypeID,
		runtime_payload: JSONObject | None = None,
	) -> None:
		enqueued_task_ids.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", fake_enqueue_started_task)

	task = await start_thread_maintenance_task(
		db_session,
		principal,
		thread_id,
	)

	assert task.id == active_task.id
	assert enqueued_task_ids == []


@pytest.mark.asyncio
async def test_start_thread_maintenance_task_supersedes_stale_active_task(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""stale active maintenance tasks are failed before a replacement starts."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_maintenance_stale@example.com",
			username="thread_maintenance_stale",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread_id = TypeID(new_typeid("thread"))
	thread = Thread(id=thread_id, owner_id=user.id, tags=[])
	db_session.add(thread)
	await db_session.flush()
	stale_at = datetime.now(tz=UTC) - timedelta(
		minutes=settings.tasks.thread_maintenance.active_supersede_after_minutes + 1
	)
	stale_task = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="starting maintenance",
		started_at=stale_at,
		last_event_at=stale_at,
		created_at=stale_at,
		updated_at=stale_at,
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: THREAD_MAINTENANCE_TASK,
			"thread_id": str(thread_id),
			"replace_metadata": False,
		},
	)
	db_session.add(stale_task)
	await db_session.commit()
	await db_session.refresh(stale_task)

	enqueued_task_ids: list[str] = []

	async def fake_enqueue_started_task(
		task_id: TypeID,
		runtime_payload: JSONObject | None = None,
	) -> None:
		enqueued_task_ids.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", fake_enqueue_started_task)

	task = await start_thread_maintenance_task(
		db_session,
		principal,
		thread_id,
	)
	await db_session.refresh(stale_task)

	assert task.id != stale_task.id
	assert stale_task.status == TaskStatus.FAILED
	assert stale_task.stage == "stale task superseded"
	assert stale_task.result == {
		"error": "stale_active_task",
		"message": "superseded by a new thread maintenance task",
		"thread_id": str(thread_id),
	}
	assert enqueued_task_ids == [str(task.id)]


@pytest.mark.asyncio
async def test_thread_inactivity_schedule_resets_future_timer(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""thread inactivity scheduling creates a resettable future timer."""
	monkeypatch.setattr(boot_settings, "TESTING", False)
	fake_source = _FakeThreadScheduleSource()
	monkeypatch.setattr(
		thread_maintenance_service, "redis_schedule_source", fake_source
	)
	user = await user_service.create_user(
		UserCreate(
			email="thread_schedule_future@example.com",
			username="thread_schedule_future",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	last_activity_at = datetime.now(tz=UTC) - timedelta(hours=1)
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		last_activity_at,
		"ready thread",
		["ready"],
	)

	scheduled = await schedule_thread_inactivity_maintenance(thread.id, db_session)
	expected_due_at = last_activity_at + timedelta(
		hours=settings.tasks.thread_maintenance.inactivity_hours
	)
	if expected_due_at.second != 0 or expected_due_at.microsecond != 0:
		expected_due_at = expected_due_at.replace(second=0, microsecond=0) + timedelta(
			minutes=1
		)

	assert scheduled is True
	assert fake_source.deleted == [f"thread:inactivity-maintenance:{thread.id}"]
	assert fake_source.scheduled == [
		(
			f"thread:inactivity-maintenance:{thread.id}",
			expected_due_at,
			str(thread.id),
			last_activity_at.isoformat(),
		)
	]


@pytest.mark.asyncio
async def test_thread_maintenance_rules_split_mandatory_and_deferred(
	db_session: AsyncSession,
) -> None:
	"""metadata gaps are immediate; summary-only gaps are deferred."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_maintenance_rules@example.com",
			username="thread_maintenance_rules",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	missing_metadata = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
	)
	summary_only = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
		"ready thread",
		["ready"],
	)

	assert thread_maintenance_service.thread_needs_mandatory_maintenance(
		missing_metadata
	)
	assert not await thread_maintenance_service.thread_needs_deferred_maintenance(
		missing_metadata,
		db_session,
	)
	assert await thread_maintenance_service.thread_needs_maintenance(
		missing_metadata,
		db_session,
	)

	assert not thread_maintenance_service.thread_needs_mandatory_maintenance(
		summary_only
	)
	assert await thread_maintenance_service.thread_needs_deferred_maintenance(
		summary_only,
		db_session,
	)
	assert await thread_maintenance_service.thread_needs_maintenance(
		summary_only,
		db_session,
	)


@pytest.mark.asyncio
async def test_thread_inactivity_schedule_starts_mandatory_metadata_now(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""missing mandatory thread metadata starts maintenance immediately."""
	monkeypatch.setattr(boot_settings, "TESTING", False)
	fake_source = _FakeThreadScheduleSource()
	monkeypatch.setattr(
		thread_maintenance_service, "redis_schedule_source", fake_source
	)
	user = await user_service.create_user(
		UserCreate(
			email="thread_schedule_mandatory@example.com",
			username="thread_schedule_mandatory",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC) - timedelta(hours=1),
	)
	enqueued: list[tuple[str, JSONObject]] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		enqueued.append((str(task_id), runtime_payload))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	scheduled = await schedule_thread_inactivity_maintenance(thread.id, db_session)
	task = await task_service.find_active_task(
		db_session,
		THREAD_MAINTENANCE_TASK,
		{"thread_id": str(thread.id)},
	)

	assert scheduled is True
	assert fake_source.deleted == [f"thread:inactivity-maintenance:{thread.id}"]
	assert fake_source.scheduled == []
	assert task is not None
	assert task.stage == "queued mandatory metadata"
	assert enqueued == [(str(task.id), {})]


@pytest.mark.asyncio
async def test_thread_inactivity_schedule_supersedes_stale_queued_mandatory_task(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""queued mandatory metadata work cannot block a thread forever."""
	monkeypatch.setattr(boot_settings, "TESTING", False)
	fake_source = _FakeThreadScheduleSource()
	monkeypatch.setattr(
		thread_maintenance_service, "redis_schedule_source", fake_source
	)
	user = await user_service.create_user(
		UserCreate(
			email="thread_schedule_stale_queued@example.com",
			username="sched_stale_queued",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
	)
	old_event_at = datetime.now(tz=UTC) - timedelta(
		minutes=settings.tasks.thread_maintenance.queued_supersede_after_minutes + 1
	)
	active_task = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="queued mandatory metadata",
		started_at=old_event_at,
		last_event_at=old_event_at,
		created_at=old_event_at,
		updated_at=old_event_at,
		spawned_thread_id=thread.id,
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: THREAD_MAINTENANCE_TASK,
			"thread_id": str(thread.id),
			"replace_metadata": False,
			"maintenance_reason": "mandatory_metadata",
			"maintenance_source": "post_run",
		},
	)
	db_session.add(active_task)
	await db_session.commit()
	await db_session.refresh(active_task)
	enqueued: list[tuple[str, JSONObject]] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		enqueued.append((str(task_id), runtime_payload))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	scheduled = await schedule_thread_inactivity_maintenance(thread.id, db_session)
	new_task = await task_service.find_active_task(
		db_session,
		THREAD_MAINTENANCE_TASK,
		{"thread_id": str(thread.id)},
	)
	await db_session.refresh(active_task)

	assert scheduled is True
	assert fake_source.deleted == [f"thread:inactivity-maintenance:{thread.id}"]
	assert fake_source.scheduled == []
	assert active_task.status == TaskStatus.FAILED
	assert active_task.stage == "queued task superseded"
	assert active_task.result == {
		"error": "stale_queued_task",
		"message": "superseded after queued inactivity",
		"thread_id": str(thread.id),
	}
	assert new_task is not None
	assert new_task.id != active_task.id
	assert new_task.stage == "queued mandatory metadata"
	assert enqueued == [(str(new_task.id), {})]


@pytest.mark.asyncio
async def test_thread_inactivity_schedule_skips_up_to_date_thread(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""scheduling clears stale timers and skips threads that need no work."""
	monkeypatch.setattr(boot_settings, "TESTING", False)
	fake_source = _FakeThreadScheduleSource()
	monkeypatch.setattr(
		thread_maintenance_service, "redis_schedule_source", fake_source
	)

	async def _does_not_need_deferred_maintenance(
		thread: Thread,
		session: AsyncSession,
	) -> bool:
		_ = thread, session
		return False

	monkeypatch.setattr(
		thread_maintenance_service,
		"thread_needs_deferred_maintenance",
		_does_not_need_deferred_maintenance,
	)
	user = await user_service.create_user(
		UserCreate(
			email="thread_schedule_uptodate@example.com",
			username="thread_schedule_uptodate",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	last_activity_at = datetime.now(tz=UTC) - timedelta(hours=1)
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		last_activity_at,
		"ready thread",
		["ready"],
	)

	scheduled = await schedule_thread_inactivity_maintenance(thread.id, db_session)

	assert scheduled is False
	assert fake_source.deleted == [f"thread:inactivity-maintenance:{thread.id}"]
	assert fake_source.scheduled == []


@pytest.mark.asyncio
async def test_run_agent_surfaces_sdk_generation_error(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="sdk-generation-error@example.com",
			username="sdk_generation_error",
			password="secret123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	agent_id = TypeID(new_typeid("agent"))
	fake_agent = SimpleNamespace(model=None, parsed_config=None)
	fake_run_agent = _FakeBadRequestRunAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return fake_agent

	async def fake_build_agent_from_orm(*_args: object, **_kwargs: object) -> object:
		return object()

	async def fake_inject_system_instructions(
		_agent: object,
		thread: SDKThread,
		**_kwargs: object,
	) -> SDKThread:
		return thread

	async def fake_prepare_steering(
		**_kwargs: object,
	) -> _FakeBadRequestRunAgent:
		return fake_run_agent

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution,
		"build_agent_from_orm",
		fake_build_agent_from_orm,
	)
	monkeypatch.setattr(
		"api.v1.service.runs.thread_context.inject_system_instructions",
		fake_inject_system_instructions,
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	terminated: list[tuple[str, TypeID | None]] = []
	original_terminate = run_execution.terminate_run

	async def capture_terminate(
		run_id: TypeID,
		reason: str,
		partial_message_id: TypeID | None = None,
	) -> object | None:
		terminated.append((reason, partial_message_id))
		return await original_terminate(run_id, reason, partial_message_id)

	monkeypatch.setattr(run_execution, "terminate_run", capture_terminate)

	await run_execution.run_agent(
		None,
		agent_id,
		principal,
		input=MessageCreate(content=[TextContent(text="hello")]),
		persist=False,
	)
	assert terminated == [("provider_bad_request", None)]


@pytest.mark.asyncio
async def test_nonpersisted_partial_failure_has_no_message_id(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="sdk-partial-generation-error@example.com",
			username="sdk_partial_generation_error",
			password="secret123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	agent_id = TypeID(new_typeid("agent"))
	fake_agent = SimpleNamespace(model=None, parsed_config=None)
	fake_run_agent = _FakePartialBadRequestRunAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return fake_agent

	async def fake_build_agent_from_orm(*_args: object, **_kwargs: object) -> object:
		return object()

	async def fake_inject_system_instructions(
		_agent: object,
		thread: SDKThread,
		**_kwargs: object,
	) -> SDKThread:
		return thread

	async def fake_prepare_steering(
		**_kwargs: object,
	) -> _FakePartialBadRequestRunAgent:
		return fake_run_agent

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution,
		"build_agent_from_orm",
		fake_build_agent_from_orm,
	)
	monkeypatch.setattr(
		"api.v1.service.runs.thread_context.inject_system_instructions",
		fake_inject_system_instructions,
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	terminated: list[tuple[str, TypeID | None]] = []
	original_terminate = run_execution.terminate_run

	async def capture_terminate(
		run_id: TypeID,
		reason: str,
		partial_message_id: TypeID | None = None,
	) -> object | None:
		terminated.append((reason, partial_message_id))
		return await original_terminate(run_id, reason, partial_message_id)

	monkeypatch.setattr(run_execution, "terminate_run", capture_terminate)

	await run_execution.run_agent(
		None,
		agent_id,
		principal,
		input=MessageCreate(content=[TextContent(text="hello")]),
		persist=False,
	)
	assert terminated == [("provider_bad_request", None)]


@pytest.mark.asyncio
async def test_run_agent_schedules_new_thread_maintenance_before_done(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a first completed chat run schedules maintenance before clients see done."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_run_schedule@example.com",
			username="thread_run_schedule",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread_id = TypeID(new_typeid("thread"))
	db_session.add(Thread(id=thread_id, owner_id=user.id, title=None, tags=[]))
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"thread-run-scheduler-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()

	fake_run_agent = _FakeCompletedRunAgent()
	scheduled_thread_ids: list[str] = []
	scheduled_threads_needed_maintenance: list[bool] = []

	async def fake_load_agent(
		*_args: object,
		**_kwargs: object,
	) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(
		**kwargs: object,
	) -> _FakeCompletedRunAgent:
		assert kwargs["sdk_agent"] is fake_run_agent
		return fake_run_agent

	async def fake_broadcast_run_event(
		*_args: object,
		**_kwargs: object,
	) -> None:
		return None

	async def capture_schedule(
		scheduled_thread_id: TypeID,
		task_session: AsyncSession | None = None,
	) -> bool:
		terminal_order.append("schedule")
		if task_session is None:
			scheduled_thread_ids.append("missing-session")
			scheduled_threads_needed_maintenance.append(False)
			return False
		scheduled_thread_ids.append(str(scheduled_thread_id))
		thread = await task_session.get(Thread, scheduled_thread_id)
		if thread is None or thread.current_message_id is None:
			scheduled_threads_needed_maintenance.append(False)
			return False
		scheduled_threads_needed_maintenance.append(
			await thread_maintenance_service.thread_needs_maintenance(
				thread,
				task_session,
			)
		)
		return True

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution,
		"build_agent_from_orm",
		fake_build_agent_from_orm,
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", fake_broadcast_run_event)
	monkeypatch.setattr(
		run_execution,
		"schedule_post_run_thread_upkeep",
		capture_schedule,
	)
	terminal_order: list[str] = []
	original_complete_run = run_execution.run_registry.complete_run

	async def capture_complete_run(run_id: TypeID) -> object | None:
		terminal_order.append("complete")
		return await original_complete_run(run_id)

	monkeypatch.setattr(
		run_execution.run_registry,
		"complete_run",
		capture_complete_run,
	)

	persisted_input = await _persist_run_input(
		db_session,
		thread_id,
		MessageCreate(content=[TextContent(text="hello")]),
		principal,
	)
	await run_execution.run_agent(
		thread_id,
		agent.id,
		principal,
		persist=True,
		persisted_input=persisted_input,
	)
	assert scheduled_thread_ids == [str(thread_id)]
	assert scheduled_threads_needed_maintenance == [True]
	assert terminal_order == ["schedule", "complete"]


@pytest.mark.asyncio
async def test_run_agent_resolves_final_assistant_reference_after_persist(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the final assistant reference resolves to the persisted message id."""
	user = await user_service.create_user(
		UserCreate(
			email="thread-run-memory-reference@example.com",
			username="thread_run_memory_reference",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread_id = TypeID(new_typeid("thread"))
	thread = Thread(id=thread_id, owner_id=user.id, title=None, tags=[])
	db_session.add(thread)
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"thread-run-memory-{new_typeid('agent')[-12:]}",
			plugin_ids=["memory_post_processing"],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()

	fake_run_agent = _FakeCompletedRunAgent()
	resolved_refs: list[tuple[str, TypeID | str]] = []
	rejected_refs: list[tuple[str, str]] = []
	terminal_order: list[str] = []

	async def fake_load_agent(
		*_args: object,
		**_kwargs: object,
	) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(
		**kwargs: object,
	) -> _FakeCompletedRunAgent:
		assert kwargs["sdk_agent"] is fake_run_agent
		return fake_run_agent

	async def fake_broadcast_run_event(
		*_args: object,
		**_kwargs: object,
	) -> None:
		return None

	async def fake_resolve_message_reference(
		reference_id: str,
		message_id: str | TypeID,
	) -> bool:
		terminal_order.append("resolve")
		resolved_refs.append((reference_id, message_id))
		return True

	async def fake_reject_message_reference(reference_id: str, reason: str) -> bool:
		rejected_refs.append((reference_id, reason))
		return True

	async def fake_schedule_thread_inactivity(
		scheduled_thread_id: TypeID,
		task_session: AsyncSession | None = None,
	) -> bool:
		_ = scheduled_thread_id, task_session
		terminal_order.append("maintenance")
		return True

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution,
		"build_agent_from_orm",
		fake_build_agent_from_orm,
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", fake_broadcast_run_event)
	monkeypatch.setattr(
		run_execution,
		"new_message_reference",
		lambda: "msg_ref_thread_run_memory",
	)
	monkeypatch.setattr(
		run_execution,
		"resolve_message_reference",
		fake_resolve_message_reference,
	)
	monkeypatch.setattr(
		run_execution,
		"reject_message_reference",
		fake_reject_message_reference,
	)
	monkeypatch.setattr(
		run_execution,
		"schedule_post_run_thread_upkeep",
		fake_schedule_thread_inactivity,
	)

	persisted_input = await _persist_run_input(
		db_session,
		thread_id,
		MessageCreate(content=[TextContent(text="hello")]),
		principal,
	)
	await run_execution.run_agent(
		thread_id,
		agent.id,
		principal,
		persist=True,
		persisted_input=persisted_input,
	)

	await db_session.refresh(thread)
	assert [
		(reference_id, str(message_id)) for reference_id, message_id in resolved_refs
	] == [("msg_ref_thread_run_memory", str(thread.current_message_id))]
	assert rejected_refs == []
	assert terminal_order == ["resolve", "maintenance"]


@pytest.mark.asyncio
async def test_run_agent_schedules_regenerated_thread_maintenance(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a completed regenerate on missing metadata starts maintenance promptly."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_regen_schedule@example.com",
			username="thread_regen_schedule",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
	)
	parent_id = TypeID(thread.current_message_id)
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"thread-regen-scheduler-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()

	fake_run_agent = _FakeCompletedRunAgent()
	scheduled_current_message_ids: list[str | None] = []
	scheduled_threads_needed_maintenance: list[bool] = []
	terminal_order: list[str] = []

	async def fake_load_agent(
		*_args: object,
		**_kwargs: object,
	) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(
		**kwargs: object,
	) -> _FakeCompletedRunAgent:
		assert kwargs["sdk_agent"] is fake_run_agent
		return fake_run_agent

	async def fake_broadcast_run_event(
		*_args: object,
		**_kwargs: object,
	) -> None:
		return None

	async def capture_schedule(
		scheduled_thread_id: TypeID,
		task_session: AsyncSession | None = None,
	) -> bool:
		terminal_order.append("schedule")
		if task_session is None:
			scheduled_current_message_ids.append(None)
			scheduled_threads_needed_maintenance.append(False)
			return False
		thread_row = await task_session.get(Thread, scheduled_thread_id)
		scheduled_current_message_ids.append(
			str(thread_row.current_message_id) if thread_row else None
		)
		scheduled_threads_needed_maintenance.append(
			bool(
				thread_row is not None
				and await thread_maintenance_service.thread_needs_maintenance(
					thread_row,
					task_session,
				)
			)
		)
		return True

	original_complete_run = run_execution.run_registry.complete_run

	async def capture_complete_run(run_id: TypeID) -> object | None:
		terminal_order.append("complete")
		return await original_complete_run(run_id)

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution,
		"build_agent_from_orm",
		fake_build_agent_from_orm,
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", fake_broadcast_run_event)
	monkeypatch.setattr(
		run_execution,
		"schedule_post_run_thread_upkeep",
		capture_schedule,
	)
	monkeypatch.setattr(
		run_execution.run_registry,
		"complete_run",
		capture_complete_run,
	)

	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		input=None,
		splice=MessageSplice(parent_id=parent_id),
		persist=True,
	)

	assert len(scheduled_current_message_ids) == 1
	assert scheduled_current_message_ids[0] is not None
	assert scheduled_current_message_ids[0] != str(parent_id)
	assert scheduled_threads_needed_maintenance == [True]
	assert terminal_order == ["schedule", "complete"]


@pytest.mark.asyncio
async def test_run_agent_regeneration_forks_from_prior_output(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="thread_regen_branch@example.com",
			username="thread_regen_branch",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
	)
	invocation_id = thread.current_message_id
	assert invocation_id is not None
	first = AssistantMessage(
		thread_id=thread.id,
		parent_id=invocation_id,
		type=MessageType.ASSISTANT,
		content=[{"type": "text", "text": "first answer"}],
		metadata_={"run_id": str(new_typeid("run"))},
	)
	db_session.add(first)
	await db_session.flush()
	thread.current_message_id = first.id
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"thread-regen-branch-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()

	fake_run_agent = _FakeCompletedRunAgent()

	async def fake_load_agent(
		*_args: object,
		**_kwargs: object,
	) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(
		**kwargs: object,
	) -> _FakeCompletedRunAgent:
		assert kwargs["sdk_agent"] is fake_run_agent
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution,
		"build_agent_from_orm",
		fake_build_agent_from_orm,
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)

	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		input=None,
		splice=MessageSplice(parent_id=invocation_id),
		persist=True,
	)

	await db_session.refresh(first)
	await db_session.refresh(thread)
	assert first.parent_id == invocation_id
	assert thread.current_message_id != first.id
	second = await db_session.get(Message, thread.current_message_id)
	assert second is not None
	assert second.parent_id == invocation_id


@pytest.mark.asyncio
async def test_run_agent_replaces_block_on_first_completed_message(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="thread_replace_run@example.com",
			username="thread_replace_run",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
	)
	anchor_id = thread.current_message_id
	assert anchor_id is not None
	old_run_id = TypeID(new_typeid("run"))
	old = AssistantMessage(
		thread_id=thread.id,
		parent_id=anchor_id,
		type=MessageType.ASSISTANT,
		content=[{"type": "text", "text": "old answer"}],
		metadata_={"run_id": str(old_run_id)},
	)
	db_session.add(old)
	await db_session.flush()
	successor = UserMessage(
		thread_id=thread.id,
		parent_id=old.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "later message"}],
		sender_user_id=user.id,
	)
	db_session.add(successor)
	await db_session.flush()
	thread.current_message_id = successor.id
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"thread-replace-run-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	fake_run_agent = _FakeMultiDeltaRunAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeMultiDeltaRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(**kwargs: object) -> _FakeMultiDeltaRunAgent:
		assert kwargs["sdk_agent"] is fake_run_agent
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution,
		"build_agent_from_orm",
		fake_build_agent_from_orm,
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)
	published_frames: list[bytes] = []
	original_publish = run_execution.run_streams.publish

	async def capture_publish(run_id: TypeID, frame: bytes) -> None:
		published_frames.append(frame)
		await original_publish(run_id, frame)

	monkeypatch.setattr(run_execution.run_streams, "publish", capture_publish)
	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		splice=MessageSplice(
			parent_id=anchor_id,
			reparent_message_ids=[successor.id],
			replaces=RunBlockRef(
				run_id=old_run_id,
				run_head_message_id=old.id,
			),
		),
		persist=True,
	)
	delta_frames = [frame for frame in published_frames if b"event: delta" in frame]
	assert sum(b'"splice"' in frame for frame in delta_frames) == 1
	message_frames = [
		frame for frame in published_frames if b"event: message_created" in frame
	]
	assert message_frames, published_frames
	message_frame = message_frames[0]
	assert str(old.id).encode() in message_frame
	assert (
		await db_session.scalar(select(Message.id).where(Message.id == old.id)) is None
	)
	await db_session.refresh(successor)
	replacement = await db_session.get(Message, successor.parent_id)
	assert replacement is not None
	assert replacement.parent_id == anchor_id


@pytest.mark.asyncio
async def test_replacement_failure_before_first_complete_keeps_old_block(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="thread_replace_failure@example.com",
			username="thread_replace_failure",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
	)
	anchor_id = thread.current_message_id
	assert anchor_id is not None
	old_run_id = TypeID(new_typeid("run"))
	old = AssistantMessage(
		thread_id=thread.id,
		parent_id=anchor_id,
		type=MessageType.ASSISTANT,
		content=[{"type": "text", "text": "old answer"}],
		metadata_={"run_id": str(old_run_id)},
	)
	db_session.add(old)
	await db_session.flush()
	successor = UserMessage(
		thread_id=thread.id,
		parent_id=old.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "later message"}],
		sender_user_id=user.id,
	)
	db_session.add(successor)
	await db_session.flush()
	thread.current_message_id = successor.id
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"thread-replace-failure-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	fake_run_agent = _FakePartialBadRequestRunAgent()
	steering_readiness_checked = False

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakePartialBadRequestRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(
		ready: Callable[[], bool],
		**_kwargs: object,
	) -> _FakePartialBadRequestRunAgent:
		nonlocal steering_readiness_checked
		assert ready() is False
		steering_readiness_checked = True
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution, "build_agent_from_orm", fake_build_agent_from_orm
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)
	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		splice=MessageSplice(
			parent_id=anchor_id,
			reparent_message_ids=[successor.id],
			replaces=RunBlockRef(
				run_id=old_run_id,
				run_head_message_id=old.id,
			),
		),
		persist=True,
	)
	assert steering_readiness_checked
	assert (
		await db_session.scalar(select(Message.id).where(Message.id == old.id))
		== old.id
	)
	await db_session.refresh(successor)
	assert successor.parent_id == old.id


@pytest.mark.asyncio
async def test_replacement_failure_after_first_complete_keeps_replacement(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="thread_replace_partial_failure@example.com",
			username="thread_replace_partial_failure",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session, user.id, datetime.now(tz=UTC)
	)
	anchor_id = thread.current_message_id
	assert anchor_id is not None
	old_run_id = TypeID(new_typeid("run"))
	old = AssistantMessage(
		thread_id=thread.id,
		parent_id=anchor_id,
		type=MessageType.ASSISTANT,
		content=[{"type": "text", "text": "old answer"}],
		metadata_={"run_id": str(old_run_id)},
	)
	db_session.add(old)
	await db_session.flush()
	successor = UserMessage(
		thread_id=thread.id,
		parent_id=old.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "later message"}],
		sender_user_id=user.id,
	)
	db_session.add(successor)
	await db_session.flush()
	thread.current_message_id = successor.id
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"replace-partial-failure-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	fake_run_agent = _FakeCompletedThenPartialBadRequestRunAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedThenPartialBadRequestRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(
		**_kwargs: object,
	) -> _FakeCompletedThenPartialBadRequestRunAgent:
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution, "build_agent_from_orm", fake_build_agent_from_orm
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)
	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		splice=MessageSplice(
			parent_id=anchor_id,
			reparent_message_ids=[successor.id],
			replaces=RunBlockRef(
				run_id=old_run_id,
				run_head_message_id=old.id,
			),
		),
		persist=True,
	)
	assert (
		await db_session.scalar(select(Message.id).where(Message.id == old.id)) is None
	)
	await db_session.refresh(successor)
	partial = await db_session.get(Message, successor.parent_id)
	assert partial is not None
	assert partial.finish_reason == "error"
	first = await db_session.get(Message, partial.parent_id)
	assert first is not None
	assert first.parent_id == anchor_id


@pytest.mark.asyncio
async def test_run_input_explicit_null_creates_shared_root_sub_thread(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = await user_service.create_user(
		UserCreate(
			email="shared_send_owner@example.com",
			username="shared_send_owner",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	mate = await user_service.create_user(
		UserCreate(
			email="shared_send_mate@example.com",
			username="shared_send_mate",
			password="password123",
		),
		db_session,
	)
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session,
		owner.id,
		datetime.now(tz=UTC),
	)
	canon_head_id = thread.current_message_id
	assert canon_head_id is not None
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"shared-send-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	fake_run_agent = _FakeCompletedRunAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(**_kwargs: object) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution, "build_agent_from_orm", fake_build_agent_from_orm
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)
	message_input = MessageCreate(content=[TextContent(text="edited root")])
	persisted_input = await _persist_run_input(
		db_session,
		thread.id,
		message_input,
		principal,
		splice=MessageSplice(parent_id=None),
	)
	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		persist=True,
		persisted_input=persisted_input,
	)
	await db_session.refresh(thread)
	assert thread.current_message_id == canon_head_id
	new_messages = list(
		(
			await db_session.scalars(
				select(Message).where(
					Message.thread_id == thread.id,
					Message.id != canon_head_id,
				)
			)
		).all()
	)
	input_message = next(
		message for message in new_messages if message.type == MessageType.USER
	)
	answer = next(
		message for message in new_messages if message.type == MessageType.ASSISTANT
	)
	assert input_message.parent_id is None
	assert input_message.branch_current_message_id == answer.id
	assert answer.parent_id == input_message.id


@pytest.mark.asyncio
async def test_run_input_persists_complete_message_contract(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = await user_service.create_user(
		UserCreate(
			email="complete_run_input@example.com",
			username="complete_run_input",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session, owner.id, datetime.now(tz=UTC)
	)
	anchor_id = thread.current_message_id
	assert anchor_id is not None
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"complete-input-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	fake_run_agent = _FakeCompletedRunAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(**_kwargs: object) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution, "build_agent_from_orm", fake_build_agent_from_orm
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)
	message_input = MessageCreate(
		content=[
			TextContent(text="full input"),
			ImageContent(url="https://example.com/image.png"),
		],
		metadata={"client_marker": "kept"},
		reply_to_message_id=anchor_id,
		mentions=[
			MessageMention(type=MentionableSubjectType.USER, id=owner.id),
		],
		citations=[
			Citation(
				index=1,
				source_type=CitationSource.URL,
				source_id="https://example.com/source",
			),
		],
	)
	persisted_input = await _persist_run_input(
		db_session,
		thread.id,
		message_input,
		principal,
	)
	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		persist=True,
		persisted_input=persisted_input,
	)
	stored = await db_session.scalar(
		select(Message)
		.where(Message.thread_id == thread.id, Message.type == MessageType.USER)
		.order_by(Message.created_at.desc())
	)
	assert stored is not None
	assert stored.content == [
		{"metadata": None, "type": "text", "text": "full input"},
		{
			"metadata": None,
			"type": "image",
			"url": "https://example.com/image.png",
			"base64": None,
			"filename": None,
			"media_type": None,
		},
	]
	assert stored.public_metadata["client_marker"] == "kept"
	assert stored.reply_to_message_id == anchor_id
	await db_session.refresh(stored, attribute_names=["mention_links"])
	assert stored.mentioned_agent_ids == []
	assert stored.mentions == [{"type": "user", "id": owner.id}]
	assert stored.citations[0]["source_id"] == "https://example.com/source"


@pytest.mark.asyncio
async def test_historical_run_output_roots_shared_sub_thread(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = await user_service.create_user(
		UserCreate(
			email="historical_output_owner@example.com",
			username="historical_output_owner",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	mate = await user_service.create_user(
		UserCreate(
			email="historical_output_mate@example.com",
			username="historical_output_mate",
			password="password123",
		),
		db_session,
	)
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session, owner.id, datetime.now(tz=UTC)
	)
	anchor_id = thread.current_message_id
	assert anchor_id is not None
	newer = UserMessage(
		thread_id=thread.id,
		parent_id=anchor_id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "newer canon"}],
		sender_user_id=owner.id,
	)
	db_session.add(newer)
	await db_session.flush()
	thread.current_message_id = newer.id
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"historical-output-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	fake_run_agent = _FakeCompletedRunAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def fake_prepare_steering(**_kwargs: object) -> _FakeCompletedRunAgent:
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution, "build_agent_from_orm", fake_build_agent_from_orm
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)
	bound_containers: list[TypeID | None] = []
	original_bind = run_execution.run_conversations.bind
	original_set_container = run_execution.run_conversations.set_container

	async def capture_bind(
		run_id: TypeID,
		container_root_id: TypeID | None,
		invocation_message_id: TypeID | None,
		read_through_message_id: TypeID | None = None,
		anchor_message_id: TypeID | None = None,
	) -> None:
		bound_containers.append(container_root_id)
		await original_bind(
			run_id,
			container_root_id,
			invocation_message_id,
			read_through_message_id,
			anchor_message_id,
		)

	monkeypatch.setattr(run_execution.run_conversations, "bind", capture_bind)

	async def capture_set_container(
		run_id: TypeID,
		container_root_id: TypeID | None,
	) -> None:
		bound_containers.append(container_root_id)
		await original_set_container(run_id, container_root_id)

	monkeypatch.setattr(
		run_execution.run_conversations,
		"set_container",
		capture_set_container,
	)
	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		splice=MessageSplice(parent_id=anchor_id),
		persist=True,
	)
	await db_session.refresh(thread)
	assert thread.current_message_id == newer.id
	generated = await db_session.scalar(
		select(Message)
		.where(
			Message.thread_id == thread.id,
			Message.type == MessageType.ASSISTANT,
		)
		.order_by(Message.created_at.desc())
	)
	assert generated is not None
	assert generated.parent_id == anchor_id
	assert generated.branch_current_message_id == generated.id
	assert bound_containers[-1] == generated.id


@pytest.mark.asyncio
async def test_blocked_sub_thread_output_keeps_run_container(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = await user_service.create_user(
		UserCreate(
			email="blocked-container-owner@example.com",
			username="blocked_container_owner",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	mate = await user_service.create_user(
		UserCreate(
			email="blocked-container-mate@example.com",
			username="blocked_container_mate",
			password="password123",
		),
		db_session,
	)
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _create_thread_with_current_message(
		db_session,
		owner.id,
		datetime.now(tz=UTC),
	)
	anchor_id = thread.current_message_id
	assert anchor_id is not None
	canon_tail = UserMessage(
		thread_id=thread.id,
		parent_id=anchor_id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "canon tail"}],
		sender_user_id=owner.id,
	)
	db_session.add(canon_tail)
	await db_session.flush()
	thread.current_message_id = canon_tail.id
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	sub_root = UserMessage(
		thread_id=thread.id,
		parent_id=anchor_id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "sub-thread root"}],
		sender_user_id=owner.id,
	)
	db_session.add(sub_root)
	await db_session.flush()
	sub_root.branch_current_message_id = sub_root.id
	agent = await agent_service.create_agent(
		AgentCreate(
			name=f"blocked-container-{new_typeid('agent')[-12:]}",
			plugin_ids=[],
			config=AgentConfig(),
		),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	first_output_persisted = asyncio.Event()

	class _TwoAnswerAgent:
		async def run(
			self,
			*_args: object,
			**_kwargs: object,
		) -> AsyncIterator[AgentDelta]:
			async def stream() -> AsyncIterator[AgentDelta]:
				yield AgentDelta(
					chat=ChatModelDelta(
						message=SDKAssistantMessage.from_text(
							"first answer"
						).model_copy(update={"finish_reason": "stop"}),
						done=True,
					),
					chunk_index=0,
				)
				await first_output_persisted.wait()
				yield AgentDelta(
					chat=ChatModelDelta(
						message=SDKAssistantMessage.from_text(
							"second answer"
						).model_copy(update={"finish_reason": "stop"}),
						done=True,
					),
					chunk_index=1,
				)
				yield AgentDelta.done_sentinel(chunk_index=2)

			return stream()

	fake_run_agent = _TwoAnswerAgent()

	async def fake_load_agent(*_args: object, **_kwargs: object) -> object:
		return agent

	async def fake_build_agent_from_orm(
		*_args: object,
		**_kwargs: object,
	) -> _TwoAnswerAgent:
		return fake_run_agent

	async def fake_prepare_steering(**_kwargs: object) -> _TwoAnswerAgent:
		return fake_run_agent

	async def noop(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_execution, "load_agent_for_run", fake_load_agent)
	monkeypatch.setattr(
		run_execution, "build_agent_from_orm", fake_build_agent_from_orm
	)
	monkeypatch.setattr(run_execution, "prepare_steering", fake_prepare_steering)
	monkeypatch.setattr(run_execution, "broadcast_run_event", noop)
	monkeypatch.setattr(run_execution, "schedule_post_run_thread_upkeep", noop)
	set_containers: list[TypeID | None] = []

	async def capture_set_container(
		_run_id: TypeID,
		container_root_id: TypeID | None,
	) -> None:
		set_containers.append(container_root_id)
		if len(set_containers) != 1:
			return
		first_output = await db_session.scalar(
			select(Message)
			.where(
				Message.thread_id == thread.id,
				Message.type == MessageType.ASSISTANT,
			)
			.order_by(Message.created_at.desc())
		)
		assert first_output is not None
		unseen = UserMessage(
			thread_id=thread.id,
			parent_id=first_output.id,
			type=MessageType.USER,
			content=[{"type": "text", "text": "unseen"}],
			sender_user_id=mate.id,
		)
		db_session.add(unseen)
		await db_session.flush()
		sub_root.branch_current_message_id = unseen.id
		await db_session.commit()
		first_output_persisted.set()

	monkeypatch.setattr(
		run_execution.run_conversations,
		"set_container",
		capture_set_container,
	)
	await run_execution.run_agent(
		thread.id,
		agent.id,
		principal,
		splice=MessageSplice(
			parent_id=sub_root.id,
			leaf=BranchLeaf(kind="branch", root_id=sub_root.id),
		),
		persist=True,
	)
	assert set_containers == [sub_root.id]


@pytest.mark.asyncio
async def test_thread_inactivity_schedule_does_not_retroactively_enqueue(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""past-due inactive threads are not scheduled retroactively by default."""
	monkeypatch.setattr(boot_settings, "TESTING", False)
	fake_source = _FakeThreadScheduleSource()
	monkeypatch.setattr(
		thread_maintenance_service, "redis_schedule_source", fake_source
	)
	user = await user_service.create_user(
		UserCreate(
			email="thread_schedule_past@example.com",
			username="thread_schedule_past",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC)
		- timedelta(hours=settings.tasks.thread_maintenance.inactivity_hours + 1),
		"ready thread",
		["ready"],
	)

	scheduled = await schedule_thread_inactivity_maintenance(thread.id, db_session)

	assert scheduled is False
	assert fake_source.deleted == [f"thread:inactivity-maintenance:{thread.id}"]
	assert fake_source.scheduled == []


@pytest.mark.asyncio
async def test_fail_stale_thread_related_tasks_marks_old_active_tasks_failed(
	db_session: AsyncSession,
) -> None:
	"""startup cleanup fails old active thread-related tasks."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_tasks_stale@example.com",
			username="thread_tasks_stale",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	stale_at = datetime.now(tz=UTC) - timedelta(hours=2)
	fresh_at = datetime.now(tz=UTC)
	stale_task = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=10,
		stage="generating",
		started_at=stale_at,
		last_event_at=stale_at,
		created_at=stale_at,
		updated_at=stale_at,
		metadata_={task_service.TASK_NAME_METADATA_KEY: THREAD_MAINTENANCE_TASK},
	)
	fresh_task = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=10,
		stage="generating",
		started_at=fresh_at,
		last_event_at=fresh_at,
		metadata_={task_service.TASK_NAME_METADATA_KEY: THREAD_MAINTENANCE_TASK},
	)
	db_session.add_all([stale_task, fresh_task])
	await db_session.commit()

	failed_count = await fail_stale_thread_related_tasks()
	await db_session.refresh(stale_task)
	await db_session.refresh(fresh_task)

	assert failed_count == 1
	assert stale_task.status == TaskStatus.FAILED
	assert stale_task.stage == "stale task failed"
	assert stale_task.result is not None
	assert stale_task.result["error"] == "stale_active_task"
	assert fresh_task.status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_task_runner_timeout_marks_task_failed(
	db_session: AsyncSession,
) -> None:
	"""registered runner timeouts fail tasks instead of leaving them active."""
	runner_name = "tests.taskiq.timeout"
	original_runners = dict(task_service._task_runners)
	original_timeouts = dict(task_service._task_runner_timeouts)
	user = await user_service.create_user(
		UserCreate(
			email="task_runner_timeout@example.com",
			username="task_runner_timeout",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	task = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="queued",
		started_at=datetime.now(tz=UTC),
		last_event_at=datetime.now(tz=UTC),
		metadata_={task_service.TASK_NAME_METADATA_KEY: runner_name},
	)
	db_session.add(task)
	await db_session.commit()
	await db_session.refresh(task)

	@task_service.register_task_runner(runner_name, timeout_seconds=lambda: 0.01)
	async def _runner(ctx: task_service.TaskContext) -> JSONObject:
		_ = ctx
		await asyncio.sleep(1)
		return {"ok": True}

	try:
		with pytest.raises(TimeoutError):
			await task_service.execute_started_task(task.id)
		await db_session.refresh(task)
		assert task.status == TaskStatus.FAILED
		assert task.stage == "timed out"
		assert task.result == {
			"error": "TimeoutError",
			"message": "task runner exceeded its timeout",
		}
	finally:
		task_service._task_runners.clear()
		task_service._task_runners.update(original_runners)
		task_service._task_runner_timeouts.clear()
		task_service._task_runner_timeouts.update(original_timeouts)


@pytest.mark.asyncio
async def test_thread_maintenance_runner_commits_summary_rows(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""maintenance runner commits generated summaries from its owned session."""
	user = await user_service.create_user(
		UserCreate(
			email="thread_maintenance_runner@example.com",
			username="thread_maintenance_runner",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC),
	)
	task = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="queued",
		started_at=datetime.now(tz=UTC),
		last_event_at=datetime.now(tz=UTC),
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: THREAD_MAINTENANCE_TASK,
			"thread_id": str(thread.id),
			"replace_metadata": False,
		},
	)
	db_session.add(task)
	await db_session.commit()
	await db_session.refresh(task)

	async def _resolve_model(
		session: AsyncSession,
		task_name: str,
	) -> object:
		_ = (session, task_name)
		return object()

	async def _run_structured(
		chat_model: object,
		thread: object,
		json_schema: dict[str, object],
		purpose: str = "structured_output",
	) -> dict[str, object]:
		_ = (chat_model, thread, json_schema)
		assert purpose == "thread_maintenance"
		return {
			"title": "project notes",
			"tags": ["project"],
			"summary": "The user started a project thread.",
			"emoji": "📝",
		}

	monkeypatch.setattr(
		thread_maintenance_service, "resolve_task_chat_model", _resolve_model
	)
	monkeypatch.setattr(
		thread_maintenance_service, "run_chat_model_json_schema", _run_structured
	)

	async def _fetch_acl_metadata(*args: object) -> dict[str, dict[str, object]]:
		resource_ids = args[0]
		assert isinstance(resource_ids, list)
		return {str(resource_id): {} for resource_id in resource_ids}

	async def _vectorize_resource(**kwargs: object) -> None:
		_ = kwargs

	monkeypatch.setattr(
		thread_maintenance_service,
		"fetch_bulk_acl_metadata",
		_fetch_acl_metadata,
	)
	monkeypatch.setattr(
		thread_maintenance_service,
		"vectorize_resource",
		_vectorize_resource,
	)
	context = task_service.TaskContext(
		task_id=task.id,
		user_id=user.id,
		metadata=task.metadata_ or {},
		runtime={},
	)

	result = await run_thread_maintenance_task(context)
	summaries = await summary_service.list_active_summaries(
		thread.id,
		db_session,
		purpose=SummaryPurpose.CATALOG,
	)

	assert result is not None
	assert result["summary_updated"] is True
	assert len(summaries) == 1
	assert summaries[0].purpose == SummaryPurpose.CATALOG
	assert summaries[0].content == "The user started a project thread."


@pytest.mark.asyncio
async def test_task_registry_exposes_static_schedules() -> None:
	"""thread inactivity maintenance is not registered as a fixed cron schedule."""
	from api.tasks import registry as task_registry_module

	assert task_registry_module is not None

	source = LabelScheduleSource(broker)
	await source.startup()
	schedules = await source.get_schedules()
	task_names = {schedule.task_name for schedule in schedules}
	assert "reminders.dispatch_due_notifications" not in task_names
	assert "calendar.dispatch_due_notifications" not in task_names
	assert THREAD_INACTIVITY_DISPATCH_TASK not in task_names


@pytest.mark.asyncio
async def test_taskiq_worker_lifecycle_starts_process_runtime(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""worker startup opens the process runtime and writes a heartbeat."""
	from api import taskiq

	calls: list[str] = []

	async def fake_start_runtime() -> None:
		calls.append("runtime:start")

	async def fake_stop_runtime() -> None:
		calls.append("runtime:stop")

	async def fake_start_process_status(role: taskiq.TaskiqProcessRole) -> None:
		calls.append(f"start:{role}")

	async def fake_stop_process_status(role: taskiq.TaskiqProcessRole) -> None:
		calls.append(f"stop:{role}")

	monkeypatch.setattr(taskiq, "start_process_runtime", fake_start_runtime)
	monkeypatch.setattr(taskiq, "stop_process_runtime", fake_stop_runtime)
	monkeypatch.setattr(taskiq, "_start_process_status", fake_start_process_status)
	monkeypatch.setattr(taskiq, "_stop_process_status", fake_stop_process_status)

	await taskiq._start_worker_process_dependencies()
	await taskiq._stop_worker_process_dependencies()

	assert calls == ["runtime:start", "start:worker", "stop:worker", "runtime:stop"]


@pytest.mark.asyncio
async def test_taskiq_worker_lifecycle_failure_aborts_startup(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""worker startup closes the process runtime when heartbeat startup fails."""
	from api import taskiq

	calls: list[str] = []

	async def fake_start_runtime() -> None:
		calls.append("runtime:start")

	async def fake_stop_runtime() -> None:
		calls.append("runtime:stop")

	async def fake_start_process_status(role: taskiq.TaskiqProcessRole) -> None:
		calls.append(f"start:{role}")
		raise RuntimeError("status unavailable")

	async def fake_stop_process_status(role: taskiq.TaskiqProcessRole) -> None:
		calls.append(f"stop:{role}")

	monkeypatch.setattr(taskiq, "start_process_runtime", fake_start_runtime)
	monkeypatch.setattr(taskiq, "stop_process_runtime", fake_stop_runtime)
	monkeypatch.setattr(taskiq, "_start_process_status", fake_start_process_status)
	monkeypatch.setattr(taskiq, "_stop_process_status", fake_stop_process_status)

	with pytest.raises(RuntimeError, match="status unavailable"):
		await taskiq._start_worker_process_dependencies()

	assert calls == ["runtime:start", "start:worker", "stop:worker", "runtime:stop"]


@pytest.mark.asyncio
async def test_taskiq_api_startup_wait_fails_when_required_processes_missing(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""api startup fails fast when a required TaskIQ role is absent."""
	from api import taskiq

	async def fake_process_status_counts() -> dict[taskiq.TaskiqProcessRole, int]:
		return {"worker": 0, "scheduler": 1}

	monkeypatch.setattr(
		taskiq,
		"_process_status_counts",
		fake_process_status_counts,
	)

	with pytest.raises(RuntimeError, match="worker"):
		await taskiq._wait_for_required_taskiq_processes(0)


def test_taskiq_status_change_does_not_log_healthy_snapshots(
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""healthy TaskIQ status checks do not emit noisy periodic logs."""
	from api import taskiq

	counts: dict[taskiq.TaskiqProcessRole, int] = {"worker": 1, "scheduler": 1}
	caplog.clear()
	with caplog.at_level(logging.INFO, logger="api.taskiq"):
		missing_roles = taskiq._log_required_process_status_change(counts, ())

	assert missing_roles == ()
	assert caplog.records == []


def test_taskiq_auto_worker_count_uses_optional_cap() -> None:
	"""auto worker count scales with CPUs and honors the configured cap."""
	from api import taskiq

	assert taskiq._auto_worker_count(0) == 1
	assert taskiq._auto_worker_count(1) == 1
	assert taskiq._auto_worker_count(4) == 2
	assert taskiq._auto_worker_count(32) == 16
	assert taskiq._auto_worker_count(32, auto_workers_max=8) == 8


def test_taskiq_auto_worker_args_expand_in_place() -> None:
	"""TaskIQ receives an integer worker count after the backend shim runs."""
	from api import taskiq

	argv = [
		"python",
		"-m",
		"api.taskiq",
		"worker",
		"api.taskiq:broker",
		"api.tasks.registry",
		"--workers",
		"auto",
	]
	taskiq._expand_auto_worker_args(argv, worker_count=3)
	assert argv[-2:] == ["--workers", "3"]

	inline_argv = ["python", "-m", "api.taskiq", "worker", "--workers=auto"]
	taskiq._expand_auto_worker_args(inline_argv, worker_count=5)
	assert inline_argv[-1] == "--workers=5"


def test_taskiq_and_bus_redis_keys_are_namespaced() -> None:
	"""redis task/run keys stay under the shared nokodo_ai namespace."""
	from api import taskiq
	from api.settings.settings import TaskiqSettings
	from api.v1.service import tasks as task_service
	from api.v1.service.runs import bus as run_bus

	taskiq_defaults = TaskiqSettings()

	assert taskiq_defaults.queue_name.startswith("nokodo-ai:")
	assert taskiq_defaults.schedule_prefix.startswith("nokodo-ai:")
	assert taskiq._status_key("worker").startswith("nokodo-ai:taskiq:status:worker:")
	assert run_bus._bus._log_key("run_1").startswith("nokodo-ai:run:")
	assert task_service._bus._log_key("task_1").startswith("nokodo-ai:task:")


@pytest.mark.asyncio
async def test_service_list_tasks(db_session: AsyncSession) -> None:
	"""Test listing tasks directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_list@example.com",
		username="task_list_test",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	# Create tasks
	for i in range(3):
		task_in = TaskCreate(
			user_id=user.id,
			task_type=TaskType.CUSTOM,
		)
		await task_service.create_task(task_in, db_session, principal=principal)

	tasks = await task_service.list_tasks(
		db_session,
		principal=principal,
		filters=TaskListFilters(owner_id=user.id),
	)
	assert len(tasks) >= 3

	# Test filter
	tasks_pending = await task_service.list_tasks(
		db_session,
		principal=principal,
		filters=TaskListFilters(owner_id=user.id, status_filter=TaskStatus.RUNNING),
	)
	assert len(tasks_pending) >= 3


@pytest.mark.asyncio
async def test_task_update_no_changes_does_not_touch_last_event(
	db_session: AsyncSession,
) -> None:
	"""No-op update should not set last_event_at and respects user scoping."""
	user_in = UserCreate(
		email="task_no_change@example.com",
		username="task_no_change",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	task = await task_service.create_task(
		TaskCreate(user_id=user.id, task_type=TaskType.CUSTOM),
		db_session,
		principal=principal,
	)
	last_event_at = task.last_event_at

	unchanged = await task_service.update_task(
		task.id,
		TaskUpdate(),
		db_session,
		principal=principal,
	)
	assert unchanged.last_event_at == last_event_at

	filtered = await task_service.list_tasks(
		db_session,
		principal=principal,
		filters=TaskListFilters(status_filter=TaskStatus.RUNNING),
	)
	assert filtered


@pytest.mark.asyncio
async def test_service_update_task(db_session: AsyncSession) -> None:
	"""Test updating a task directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_update@example.com",
		username="task_update",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
	)
	task = await task_service.create_task(task_in, db_session, principal=principal)

	# Update
	update_in = TaskUpdate(status=TaskStatus.COMPLETED)
	updated_task = await task_service.update_task(
		task.id,
		update_in,
		db_session,
		principal=principal,
	)
	assert updated_task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_service_get_task_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent task."""
	user = await user_service.create_user(
		UserCreate(
			email="task_nf@example.com",
			username="task_nf_test",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException) as exc:
		await task_service.update_task(
			"nonexistent",
			TaskUpdate(status=TaskStatus.COMPLETED),
			db_session,
			principal=principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_service_update_task_no_changes(db_session: AsyncSession) -> None:
	"""Test updating a task with no changes."""
	# Create user and task
	user_in = UserCreate(
		email="task_no_change@example.com",
		username="task_no_change",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())
	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
	)
	task = await task_service.create_task(task_in, db_session, principal=principal)

	# Update with no changes
	update_in = TaskUpdate()
	updated_task = await task_service.update_task(
		task.id,
		update_in,
		db_session,
		principal=principal,
	)
	assert updated_task.id == task.id


# thread maintenance backfill ------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_sweep_disabled_by_default_returns_skipped() -> None:
	"""scheduled backfill sweeps no-op while the master toggle is off."""
	result = await run_thread_maintenance_backfill_sweep(respect_enabled=True)

	assert result["skipped"] is True
	assert result["reason"] == "disabled"
	assert result["dispatched"] == 0


@pytest.mark.asyncio
async def test_disabled_backfill_schedule_cleared_before_taskiq_startup(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""API boot clears stale backfill schedules before waiting on TaskIQ."""
	monkeypatch.setattr(boot_settings, "TESTING", False)
	fake_source = _FakeThreadScheduleSource()
	monkeypatch.setattr(
		thread_maintenance_service, "redis_schedule_source", fake_source
	)

	cleared = await clear_disabled_thread_maintenance_backfill_schedule()

	assert cleared is True
	assert fake_source.deleted == [THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID]


@pytest.mark.asyncio
async def test_backfill_sweep_dispatches_eligible_threads(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""manual backfill runs ignore the toggle and dispatch eligible threads."""
	user = await user_service.create_user(
		UserCreate(
			email="backfill_dispatch@example.com",
			username="backfill_dispatch",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	stale_thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC)
		- timedelta(hours=settings.tasks.thread_maintenance.inactivity_hours + 1),
	)
	await db_session.commit()

	# stub the maintenance check so the test does not depend on summary state.
	async def _needs_maintenance(thread: Thread, session: AsyncSession) -> bool:
		_ = (thread, session)
		return True

	monkeypatch.setattr(
		thread_maintenance_service,
		"thread_needs_maintenance",
		_needs_maintenance,
	)

	enqueued: list[tuple[str, JSONObject]] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		enqueued.append((str(task_id), runtime_payload))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	result = await run_thread_maintenance_backfill_sweep(
		batch_size=5,
		max_lookback_days=30,
		min_inactivity_hours=settings.tasks.thread_maintenance.inactivity_hours,
		respect_enabled=False,
	)

	assert result["dispatched"] == 1
	assert result["skipped_existing"] == 0
	assert result["batch_size"] == 5
	assert result["dispatched_thread_ids"] == [str(stale_thread.id)]
	assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_backfill_sweep_limits_candidate_inspection(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""backfill sweeps inspect no more than the configured batch size."""
	user = await user_service.create_user(
		UserCreate(
			email="backfill_batch_limit@example.com",
			username="backfill_batch_limit",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	for offset in range(4):
		await _create_thread_with_current_message(
			db_session,
			user.id,
			datetime.now(tz=UTC)
			- timedelta(
				hours=settings.tasks.thread_maintenance.inactivity_hours + 4 - offset
			),
		)
	await db_session.commit()

	checked_thread_ids: list[str] = []

	async def _needs_maintenance(thread: Thread, session: AsyncSession) -> bool:
		_ = session
		checked_thread_ids.append(str(thread.id))
		return True

	monkeypatch.setattr(
		thread_maintenance_service,
		"thread_needs_maintenance",
		_needs_maintenance,
	)

	enqueued: list[str] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		_ = runtime_payload
		enqueued.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	result = await run_thread_maintenance_backfill_sweep(
		batch_size=2,
		max_lookback_days=30,
		min_inactivity_hours=settings.tasks.thread_maintenance.inactivity_hours,
		respect_enabled=False,
	)

	assert result["dispatched"] == 2
	assert len(checked_thread_ids) == 2
	assert len(enqueued) == 2


@pytest.mark.asyncio
async def test_backfill_sweep_respects_max_lookback_days(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""threads older than the lookback window are intentionally ignored."""
	user = await user_service.create_user(
		UserCreate(
			email="backfill_lookback@example.com",
			username="backfill_lookback",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	# this thread is past the lookback window and must be excluded.
	await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC) - timedelta(days=60),
	)
	await db_session.commit()

	async def _needs_maintenance(thread: Thread, session: AsyncSession) -> bool:
		_ = (thread, session)
		return True

	monkeypatch.setattr(
		thread_maintenance_service,
		"thread_needs_maintenance",
		_needs_maintenance,
	)

	enqueued: list[str] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		_ = runtime_payload
		enqueued.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	result = await run_thread_maintenance_backfill_sweep(
		batch_size=10,
		max_lookback_days=30,
		min_inactivity_hours=settings.tasks.thread_maintenance.inactivity_hours,
		respect_enabled=False,
	)

	assert result["dispatched"] == 0
	assert enqueued == []


@pytest.mark.asyncio
async def test_backfill_sweep_skips_threads_with_active_maintenance_task(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""threads already covered by an active maintenance task are not redispatched."""
	user = await user_service.create_user(
		UserCreate(
			email="backfill_skip_existing@example.com",
			username="backfill_skip_existing",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	thread = await _create_thread_with_current_message(
		db_session,
		user.id,
		datetime.now(tz=UTC)
		- timedelta(hours=settings.tasks.thread_maintenance.inactivity_hours + 1),
	)

	# pre-existing active maintenance task for this thread.
	now = datetime.now(tz=UTC)
	existing = Task(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="queued",
		started_at=now,
		last_event_at=now,
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: THREAD_MAINTENANCE_TASK,
			"thread_id": str(thread.id),
		},
	)
	db_session.add(existing)
	await db_session.commit()

	async def _needs_maintenance(t: Thread, session: AsyncSession) -> bool:
		_ = (t, session)
		return True

	monkeypatch.setattr(
		thread_maintenance_service,
		"thread_needs_maintenance",
		_needs_maintenance,
	)

	enqueued: list[str] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		_ = runtime_payload
		enqueued.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	result = await run_thread_maintenance_backfill_sweep(
		batch_size=5,
		max_lookback_days=30,
		min_inactivity_hours=settings.tasks.thread_maintenance.inactivity_hours,
		respect_enabled=False,
	)

	assert result["dispatched"] == 0
	assert result["skipped_existing"] == 1
	assert enqueued == []


@pytest.mark.asyncio
async def test_backfill_task_is_not_a_static_label_schedule() -> None:
	"""the backfill task must not be registered as a fixed cron via labels.

	the schedule is installed dynamically via the redis schedule source so
	that admins can toggle and tune it at runtime through Settings.
	"""
	source = LabelScheduleSource(broker)
	await source.startup()
	schedules = await source.get_schedules()
	task_names = {schedule.task_name for schedule in schedules}
	assert THREAD_MAINTENANCE_BACKFILL_TASK not in task_names
