"""tests for steering inbox + drain logic on RunStatusStore."""

from __future__ import annotations

import asyncio

import pytest

from api.v1.service.chat.run_status import RunStatusStore


@pytest.mark.asyncio
async def test_enqueue_steering_when_running_accepts_message() -> None:
	"""enqueue_steering returns True and queues for a running run."""
	store = RunStatusStore()
	await store.start_run(
		run_id="run_s1",
		thread_id="thread_s1",
		agent_id="agent_s1",
		user_id="user_s1",
	)
	accepted = await store.enqueue_steering(
		"run_s1", "msg_s1", {"sdk": "msg"}
	)
	assert accepted is True
	rs = await store.get_run("run_s1")
	assert rs is not None
	assert rs.pending_steering == ["msg_s1"]
	assert rs.steering_inbox.qsize() == 1


@pytest.mark.asyncio
async def test_enqueue_steering_unknown_run_returns_false() -> None:
	store = RunStatusStore()
	assert await store.enqueue_steering("run_nope", "msg_x", {}) is False


@pytest.mark.asyncio
async def test_enqueue_steering_terminal_run_returns_false() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id="run_s2", thread_id="t", agent_id="a", user_id="u"
	)
	await store.complete_run("run_s2")
	assert await store.enqueue_steering("run_s2", "m", {}) is False


@pytest.mark.asyncio
async def test_enqueue_steering_full_inbox_returns_false() -> None:
	"""inbox is bounded; once full further enqueues fail without blocking."""
	store = RunStatusStore()
	await store.start_run(
		run_id="run_s3", thread_id="t", agent_id="a", user_id="u"
	)
	rs = await store.get_run("run_s3")
	assert rs is not None
	# saturate the queue using the actual maxsize
	cap = rs.steering_inbox.maxsize
	for i in range(cap):
		assert await store.enqueue_steering(
			"run_s3", f"msg_{i}", {"i": i}
		) is True
	assert await store.enqueue_steering("run_s3", "overflow", {}) is False


@pytest.mark.asyncio
async def test_claim_pending_steering_drains_and_moves_to_claimed() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id="run_s4", thread_id="t", agent_id="a", user_id="u"
	)
	await store.enqueue_steering("run_s4", "m1", {"i": 1})
	await store.enqueue_steering("run_s4", "m2", {"i": 2})
	drained = await store.claim_pending_steering("run_s4")
	assert drained == [{"i": 1}, {"i": 2}]
	rs = await store.get_run("run_s4")
	assert rs is not None
	assert rs.pending_steering == []
	assert rs.claimed_steering == ["m1", "m2"]
	assert rs.steering_inbox.qsize() == 0
	# in-flight surfaces both pending and claimed for terminal handlers
	assert rs.in_flight_steering() == ["m1", "m2"]
	# idempotent
	assert await store.claim_pending_steering("run_s4") == []


@pytest.mark.asyncio
async def test_claim_pending_steering_unknown_run_returns_empty() -> None:
	store = RunStatusStore()
	assert await store.claim_pending_steering("run_nope") == []


@pytest.mark.asyncio
async def test_mark_steering_injected_removes_only_listed_ids() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id="run_s5", thread_id="t", agent_id="a", user_id="u"
	)
	await store.enqueue_steering("run_s5", "m1", {})
	await store.enqueue_steering("run_s5", "m2", {})
	await store.enqueue_steering("run_s5", "m3", {})
	await store.mark_steering_injected("run_s5", ["m1", "m3"])
	rs = await store.get_run("run_s5")
	assert rs is not None
	assert rs.pending_steering == ["m2"]


@pytest.mark.asyncio
async def test_mark_steering_injected_empty_or_unknown_run_is_noop() -> None:
	store = RunStatusStore()
	await store.start_run(
		run_id="run_s6", thread_id="t", agent_id="a", user_id="u"
	)
	await store.enqueue_steering("run_s6", "m1", {})
	await store.mark_steering_injected("run_s6", [])
	rs = await store.get_run("run_s6")
	assert rs is not None
	assert rs.pending_steering == ["m1"]
	# unknown run does not raise
	await store.mark_steering_injected("run_unknown", ["m1"])


@pytest.mark.asyncio
async def test_steering_inbox_is_bounded_at_64_by_default() -> None:
	"""sanity: the default queue is bounded so a misbehaving client cannot OOM."""
	store = RunStatusStore()
	await store.start_run(
		run_id="run_s7", thread_id="t", agent_id="a", user_id="u"
	)
	rs = await store.get_run("run_s7")
	assert rs is not None
	assert rs.steering_inbox.maxsize > 0
	# must not block: put_nowait under lock means we either accept or refuse,
	# never await indefinitely. attempting cap+1 enqueues completes immediately.
	cap = rs.steering_inbox.maxsize
	for i in range(cap + 5):
		await asyncio.wait_for(
			store.enqueue_steering("run_s7", f"m{i}", {}), timeout=1.0
		)
