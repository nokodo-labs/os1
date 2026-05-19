"""tests for steering inbox + drain logic on RunStatusStore."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.schemas.runs import RunInput
from api.v1.service.auth import Principal
from api.v1.service.chat import steering as steering_service
from api.v1.service.chat.message_metadata import CLIENT_STEERING_ID_KEY
from api.v1.service.chat.run_status import RunStatusStore, run_status_store
from nokodo_ai.messages import TextContent
from nokodo_ai.utils.typeid import TypeID


@pytest.mark.asyncio
async def test_enqueue_steering_when_running_accepts_message() -> None:
	"""enqueue_steering returns True and queues for a running run."""
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s1"),
		thread_id=TypeID("thread_s1"),
		agent_id=TypeID("agent_s1"),
		user_id=TypeID("user_s1"),
	)
	accepted = await store.enqueue_steering(
		TypeID("run_s1"), TypeID("msg_s1"), {"sdk": "msg"}
	)
	assert accepted is True
	rs = await store.get_run(TypeID("run_s1"))
	assert rs is not None
	assert rs.pending_steering == ["msg_s1"]
	assert rs.steering_inbox.qsize() == 1


@pytest.mark.asyncio
async def test_enqueue_run_steering_accepts_before_subscriber_starts(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a locally registered run accepts steering before redis subscriber startup."""
	run_id = TypeID("run_direct_steer")
	thread_id = TypeID("thread_direct_steer")
	agent_id = TypeID("agent_direct_steer")
	user_id = TypeID("user_direct_steer")
	message_id = TypeID("msg_direct_steer")
	publish_called = False

	async def fake_enabled(_agent_id: TypeID, _db: object) -> bool:
		return True

	async def fake_require_access(*_args: object, **_kwargs: object) -> None:
		return None

	async def fake_resolve_input(
		_run_input: RunInput, _db: object
	) -> list[TextContent]:
		return [TextContent(text="early steer")]

	async def fake_create_user_message(
		_thread_id: TypeID,
		_db: object,
		principal: Principal,
		resolved_input: list[TextContent],
		parent_id: TypeID | None,
		run_id: TypeID,
		origin_session_id: str | None = None,
		attachment_actions: object | None = None,
		extra_metadata: dict[str, object] | None = None,
	) -> object:
		assert principal.user.id == user_id
		assert resolved_input == [TextContent(text="early steer")]
		assert parent_id is None
		assert str(run_id) == "run_direct_steer"
		assert origin_session_id is None
		assert attachment_actions is None
		assert extra_metadata is not None
		assert extra_metadata[CLIENT_STEERING_ID_KEY] == "local-steering-1"
		return SimpleNamespace(
			id=message_id,
			created_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
			metadata_=extra_metadata,
		)

	async def fake_publish_steer(*_args: object, **_kwargs: object) -> int:
		nonlocal publish_called
		publish_called = True
		return 0

	monkeypatch.setattr(steering_service, "_is_steering_enabled", fake_enabled)
	monkeypatch.setattr(steering_service, "require_thread_access", fake_require_access)
	monkeypatch.setattr(steering_service, "resolve_run_input", fake_resolve_input)
	monkeypatch.setattr(
		steering_service, "create_run_user_message", fake_create_user_message
	)
	monkeypatch.setattr(steering_service, "publish_steer", fake_publish_steer)
	# prevent fire-and-forget broadcast tasks from outliving the test
	monkeypatch.setattr(
		steering_service, "create_background_task", lambda coro, name: coro.close()
	)

	await run_status_store.start_run(run_id, agent_id, user_id, thread_id)
	try:
		db = AsyncMock(spec=AsyncSession)
		db.get.return_value = SimpleNamespace(current_message_id=None)
		principal = Principal(
			user=User(
				id=user_id,
				email="early-steer@example.com",
				username="early-steer",
				hashed_password="x",
			),
			group_ids=(),
			permissions=frozenset(),
		)
		result = await steering_service.enqueue_run_steering(
			run_id,
			RunInput(text="early steer"),
			None,
			"local-steering-1",
			principal,
			db,
		)

		assert result.state == "queued"
		assert result.message_id == message_id
		assert publish_called is False
		drained = await run_status_store.claim_pending_steering(run_id)
		assert len(drained) == 1
		assert drained[0].metadata[CLIENT_STEERING_ID_KEY] == "local-steering-1"
	finally:
		await run_status_store.complete_run(run_id)


@pytest.mark.asyncio
async def test_enqueue_steering_unknown_run_returns_false() -> None:
	store = RunStatusStore()
	assert (
		await store.enqueue_steering(TypeID("run_nope"), TypeID("msg_x"), {}) is False
	)


@pytest.mark.asyncio
async def test_enqueue_steering_terminal_run_returns_false() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s2"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.complete_run(TypeID("run_s2"))
	assert await store.enqueue_steering(TypeID("run_s2"), TypeID("m"), {}) is False


@pytest.mark.asyncio
async def test_enqueue_steering_full_inbox_returns_false() -> None:
	"""inbox is bounded; once full further enqueues fail without blocking."""
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s3"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	rs = await store.get_run(TypeID("run_s3"))
	assert rs is not None
	# saturate the queue using the actual maxsize
	cap = rs.steering_inbox.maxsize
	for i in range(cap):
		assert (
			await store.enqueue_steering(TypeID("run_s3"), TypeID(f"msg_{i}"), {"i": i})
			is True
		)
	assert (
		await store.enqueue_steering(TypeID("run_s3"), TypeID("overflow"), {}) is False
	)


@pytest.mark.asyncio
async def test_claim_pending_steering_drains_and_moves_to_claimed() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s4"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.enqueue_steering(TypeID("run_s4"), TypeID("m1"), {"i": 1})
	await store.enqueue_steering(TypeID("run_s4"), TypeID("m2"), {"i": 2})
	drained = await store.claim_pending_steering(TypeID("run_s4"))
	assert drained == [{"i": 1}, {"i": 2}]
	rs = await store.get_run(TypeID("run_s4"))
	assert rs is not None
	assert rs.pending_steering == []
	assert rs.claimed_steering == ["m1", "m2"]
	assert rs.steering_inbox.qsize() == 0
	# in-flight surfaces both pending and claimed for terminal handlers
	assert rs.in_flight_steering() == ["m1", "m2"]
	# idempotent
	assert await store.claim_pending_steering(TypeID("run_s4")) == []


@pytest.mark.asyncio
async def test_claim_pending_steering_unknown_run_returns_empty() -> None:
	store = RunStatusStore()
	assert await store.claim_pending_steering(TypeID("run_nope")) == []


@pytest.mark.asyncio
async def test_has_in_flight_steering_tracks_pending_and_claimed() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s8"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	assert await store.has_in_flight_steering(TypeID("run_s8")) is False
	await store.enqueue_steering(TypeID("run_s8"), TypeID("m1"), {"i": 1})
	assert await store.has_in_flight_steering(TypeID("run_s8")) is True
	await store.claim_pending_steering(TypeID("run_s8"))
	assert await store.has_in_flight_steering(TypeID("run_s8")) is True
	await store.mark_steering_injected(TypeID("run_s8"), [TypeID("m1")])
	assert await store.has_in_flight_steering(TypeID("run_s8")) is False


@pytest.mark.asyncio
async def test_mark_steering_injected_removes_only_listed_ids() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s5"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.enqueue_steering(TypeID("run_s5"), TypeID("m1"), {})
	await store.enqueue_steering(TypeID("run_s5"), TypeID("m2"), {})
	await store.enqueue_steering(TypeID("run_s5"), TypeID("m3"), {})
	await store.mark_steering_injected(TypeID("run_s5"), [TypeID("m1"), TypeID("m3")])
	rs = await store.get_run(TypeID("run_s5"))
	assert rs is not None
	assert rs.pending_steering == ["m2"]


@pytest.mark.asyncio
async def test_mark_steering_injected_empty_or_unknown_run_is_noop() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s6"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.enqueue_steering(TypeID("run_s6"), TypeID("m1"), {})
	await store.mark_steering_injected(TypeID("run_s6"), [])
	rs = await store.get_run(TypeID("run_s6"))
	assert rs is not None
	assert rs.pending_steering == ["m1"]
	# unknown run does not raise
	await store.mark_steering_injected(TypeID("run_unknown"), [TypeID("m1")])


@pytest.mark.asyncio
async def test_steering_inbox_is_bounded_at_64_by_default() -> None:
	"""sanity: the default queue is bounded so a misbehaving client cannot OOM."""
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_s7"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	rs = await store.get_run(TypeID("run_s7"))
	assert rs is not None
	assert rs.steering_inbox.maxsize > 0
	# must not block: put_nowait under lock means we either accept or refuse,
	# never await indefinitely. attempting cap+1 enqueues completes immediately.
	cap = rs.steering_inbox.maxsize
	for i in range(cap + 5):
		await asyncio.wait_for(
			store.enqueue_steering(TypeID("run_s7"), TypeID(f"m{i}"), {}), timeout=1.0
		)
