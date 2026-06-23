"""tests for run cancel + task tracking on RunStatusStore."""

from __future__ import annotations

import asyncio

import pytest

from api.v1.service.chat.run_status import RunState, RunStatusStore
from nokodo_ai.utils.typeid import TypeID


@pytest.mark.asyncio
async def test_attach_task_and_cancel_run_stops_task() -> None:
	"""cancel_run cancels the attached producer task."""
	store = RunStatusStore()
	rs = await store.start_run(
		run_id=TypeID("run_test_1"),
		thread_id=TypeID("thread_test_1"),
		agent_id=TypeID("agent_test_1"),
		user_id=TypeID("user_test_1"),
	)
	assert rs.state is RunState.RUNNING

	# spawn a long-running task and attach it
	async def _producer() -> None:
		await asyncio.sleep(60)

	task = asyncio.create_task(_producer())
	await store.attach_task(TypeID("run_test_1"), task)

	# cancel via store API
	cancelled = await store.cancel_run(TypeID("run_test_1"))
	assert cancelled is True

	# wait for the task to actually finish via cancellation
	with pytest.raises(asyncio.CancelledError):
		await task
	assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_run_returns_false_when_no_task() -> None:
	"""cancel_run returns False if no task is attached or run is unknown."""
	store = RunStatusStore()
	# unknown run
	assert await store.cancel_run(TypeID("run_does_not_exist")) is False

	# known run with no attached task
	await store.start_run(
		run_id=TypeID("run_test_2"),
		thread_id=TypeID("thread_test_2"),
		agent_id=TypeID("agent_test_2"),
		user_id=TypeID("user_test_2"),
	)
	assert await store.cancel_run(TypeID("run_test_2")) is False


@pytest.mark.asyncio
async def test_cancel_run_returns_false_when_task_already_done() -> None:
	"""cancel_run returns False when the attached task has already finished."""
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_test_3"),
		thread_id=TypeID("thread_test_3"),
		agent_id=TypeID("agent_test_3"),
		user_id=TypeID("user_test_3"),
	)

	async def _quick() -> None:
		return

	task = asyncio.create_task(_quick())
	await task
	await store.attach_task(TypeID("run_test_3"), task)

	assert await store.cancel_run(TypeID("run_test_3")) is False


@pytest.mark.asyncio
async def test_subscriber_disconnect_does_not_kill_run() -> None:
	"""unsubscribe only removes the queue; the run + producer state stays."""
	store = RunStatusStore()
	await store.start_run(
		run_id=TypeID("run_test_4"),
		thread_id=TypeID("thread_test_4"),
		agent_id=TypeID("agent_test_4"),
		user_id=TypeID("user_test_4"),
	)

	# simulate a producer publishing one frame, then a subscriber listening
	await store.publish(TypeID("run_test_4"), b"event: delta\ndata: {}\n\n")

	result = await store.subscribe(TypeID("run_test_4"))
	assert result is not None
	catchup, q = result
	assert len(catchup) == 1

	# subscriber disconnects
	await store.unsubscribe(TypeID("run_test_4"), q)

	# run is still alive in the store
	assert await store.get_run(TypeID("run_test_4")) is not None

	# new subscriber can still attach and gets the same catchup log
	result2 = await store.subscribe(TypeID("run_test_4"))
	assert result2 is not None
	catchup2, _q2 = result2
	assert len(catchup2) == 1
