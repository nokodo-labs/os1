"""tests for steering inbox + drain logic on RunStatusStore."""

from __future__ import annotations

import asyncio

import pytest

from api.v1.service.chat.run_status import RunStatusStore
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
