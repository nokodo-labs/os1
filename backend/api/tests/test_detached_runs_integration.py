"""integration tests for run lifecycle.

these tests exercise the full service-layer flow:
  start_thread_run -> spawn background task -> subscribe stream
without going through HTTP, but with the real run_status_store, real
RunRequest validation, and the real subscribe/publish/cancel machinery.

what they prove:
- a run keeps progressing even when the original SSE caller disconnects.
- multiple concurrent subscribers (multi-tab, multi-participant) all see
  the same frames in the same order.
- a late subscriber receives the full catchup log + continues live.
- cancel_run via the store really stops the producer task and releases
  every subscriber.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from api.v1.service import runs as runs_service
from api.v1.service.chat.run_status import RunState, run_status_store
from nokodo_ai.utils.typeid import TypeID, new_typeid


pytestmark = pytest.mark.asyncio


# ---- controllable fake agent ---------------------------------------------


@dataclass
class _FakeAgent:
	"""controllable stand-in for chat_run_agent.

	follows the real protocol: registers the run in the store, sets
	``ready_event``, then publishes frames whenever ``advance`` is set.
	terminates and calls ``complete_run`` when ``finish`` is set.
	"""

	advance: asyncio.Event = field(default_factory=asyncio.Event)
	finish: asyncio.Event = field(default_factory=asyncio.Event)
	started: asyncio.Event = field(default_factory=asyncio.Event)
	frames_published: int = 0
	run_id: TypeID | None = None

	def __call__(
		self,
		thread_id: TypeID,
		agent_id: TypeID,
		principal: object,
		*,
		run_id_override: TypeID,
		ready_event: asyncio.Event,
		**_kwargs: object,
	) -> AsyncIterator[bytes]:
		return self._gen(thread_id, agent_id, principal, run_id_override, ready_event)

	async def _gen(
		self,
		thread_id: TypeID,
		agent_id: TypeID,
		principal: object,
		run_id: TypeID,
		ready_event: asyncio.Event,
	) -> AsyncIterator[bytes]:
		self.run_id = run_id
		await run_status_store.start_run(
			run_id=run_id,
			thread_id=thread_id,
			agent_id=agent_id,
			user_id=getattr(principal, "user_id", "test-user"),
		)
		# mirror real run_agent: self-attach the current task so cancel_run
		# works from the very first instant the run is visible.
		current = asyncio.current_task()
		if current is not None:
			await run_status_store.attach_task(run_id, current)
		ready_event.set()
		self.started.set()

		# publish an initial frame so subscribers see something on connect
		await self._publish(b"event: delta\ndata: {\"i\":0}\n\n")

		# loop publishing one frame per advance signal
		while not self.finish.is_set():
			adv_task = asyncio.create_task(self.advance.wait())
			fin_task = asyncio.create_task(self.finish.wait())
			try:
				await asyncio.wait(
					[adv_task, fin_task],
					return_when=asyncio.FIRST_COMPLETED,
				)
			finally:
				for t in (adv_task, fin_task):
					if not t.done():
						t.cancel()
						try:
							await t
						except (asyncio.CancelledError, BaseException):
							pass
			if self.finish.is_set():
				break
			self.advance.clear()
			await self._publish(
				f"event: delta\ndata: {{\"i\":{self.frames_published}}}\n\n".encode()
			)

		await run_status_store.complete_run(run_id)
		# generator with no yields - the driver discards everything anyway
		if False:
			yield b""

	async def _publish(self, frame: bytes) -> None:
		assert self.run_id is not None
		await run_status_store.publish(self.run_id, frame)
		self.frames_published += 1


@pytest.fixture
def fake_principal() -> object:
	class _U:
		id = "user_test_detached"

	class _P:
		user_id = "user_test_detached"
		user = _U()

	return _P()


@pytest.fixture
def thread_id() -> TypeID:
	return TypeID(new_typeid("thread"))


@pytest.fixture
def agent_id() -> TypeID:
	return TypeID(new_typeid("agent"))


# ---- tests ---------------------------------------------------------------


async def test_run_outlives_subscriber_disconnect(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: object,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""subscriber disconnects mid-run; producer survives; late subscriber catches up."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,  # type: ignore[arg-type]
		input=None,
		parent_id=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
	)

	# first subscriber gets the initial frame, then disconnects
	stream1 = runs_service.subscribe_run_stream(run_id)
	first = await asyncio.wait_for(stream1.__anext__(), timeout=2.0)
	assert b"\"i\":0" in first
	await stream1.aclose()

	# producer publishes 2 more frames while NOBODY is subscribed
	fake.advance.set()
	# small yield so producer task picks up the advance signal
	await asyncio.sleep(0.05)
	fake.advance.set()
	await asyncio.sleep(0.05)

	# late subscriber connects - must get full catchup (3 frames so far)
	stream2 = runs_service.subscribe_run_stream(run_id)
	collected: list[bytes] = []
	for _ in range(3):
		collected.append(await asyncio.wait_for(stream2.__anext__(), timeout=2.0))
	assert any(b"\"i\":0" in f for f in collected)
	assert any(b"\"i\":1" in f for f in collected)
	assert any(b"\"i\":2" in f for f in collected)

	# finish the run cleanly
	fake.finish.set()
	# drain remaining (done sentinel)
	async for _ in stream2:
		pass

	# run is gone
	assert await run_status_store.get_run(run_id) is None


async def test_multiple_concurrent_subscribers_get_same_frames(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: object,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""two subscribers attached at the same time both observe every live frame."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,  # type: ignore[arg-type]
		input=None,
		parent_id=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
	)

	stream_a = runs_service.subscribe_run_stream(run_id)
	stream_b = runs_service.subscribe_run_stream(run_id)

	# both consume the catchup frame (i=0)
	a0 = await asyncio.wait_for(stream_a.__anext__(), timeout=2.0)
	b0 = await asyncio.wait_for(stream_b.__anext__(), timeout=2.0)
	assert a0 == b0

	# advance once - both must observe the new frame
	fake.advance.set()
	a1 = await asyncio.wait_for(stream_a.__anext__(), timeout=2.0)
	b1 = await asyncio.wait_for(stream_b.__anext__(), timeout=2.0)
	assert a1 == b1
	assert b"\"i\":1" in a1

	fake.finish.set()
	async for _ in stream_a:
		pass
	async for _ in stream_b:
		pass


async def test_cancel_run_terminates_producer_and_unblocks_subscribers(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: object,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""cancel_run via the store stops the producer task and ends every stream."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,  # type: ignore[arg-type]
		input=None,
		parent_id=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
	)

	stream = runs_service.subscribe_run_stream(run_id)
	# consume initial frame so the loop is established
	await asyncio.wait_for(stream.__anext__(), timeout=2.0)

	# cancel via the store - simulates POST /threads/{tid}/runs/{rid}/cancel
	cancelled = await run_status_store.cancel_run(run_id)
	assert cancelled is True

	# subscriber must terminate (queue gets None sentinel from fail_run broadcast)
	with pytest.raises(StopAsyncIteration):
		# pump until exhaustion - we expect the stream to end shortly
		async def _drain() -> None:
			async for _ in stream:
				pass
			raise StopAsyncIteration

		await asyncio.wait_for(_drain(), timeout=2.0)

	# run is no longer registered
	assert await run_status_store.get_run(run_id) is None
	# producer task was actually cancelled - state should be FAILED before removal
	# (already removed; we just confirm the in-memory row is gone above)
	# additionally: a fresh cancel returns False
	assert await run_status_store.cancel_run(run_id) is False


async def test_late_subscriber_after_eviction_raises_unknown_run(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: object,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""late subscribers within the grace window get a clean done; after
	the redis catchup log expires they get ``UnknownRunError``.

	the catchup log persists for a short grace after the producer
	terminates so cross-worker subscribers landing in the
	mark_run_end / LRANGE race window still see the completed stream.
	the log carries an explicit end marker so subscribers detect
	completion without blocking on a pubsub message they missed.
	"""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,  # type: ignore[arg-type]
		input=None,
		parent_id=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
	)

	# finish immediately and wait for store to clear
	fake.finish.set()
	for _ in range(50):
		if await run_status_store.get_run(run_id) is None:
			break
		await asyncio.sleep(0.02)

	# within the catchup grace window: late subscriber drains cleanly
	# (catchup frames + synthesized done, no hang) without UnknownRunError.
	frames = [f async for f in runs_service.subscribe_run_stream(run_id)]
	assert any(b"event: done" in f for f in frames)

	# after the catchup log expires (DELETE the key to simulate post-grace),
	# late subscribers raise UnknownRunError.
	from api.redis import redis_client
	from api.v1.service.chat.run_bus import _log_key  # type: ignore[attr-defined]

	await redis_client.get().delete(_log_key(run_id))

	stream = runs_service.subscribe_run_stream(run_id)
	with pytest.raises(runs_service.UnknownRunError):
		_ = [f async for f in stream]


async def test_state_is_running_while_first_subscriber_attached(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: object,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""sanity: store shows RUNNING state once attach_task completes."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,  # type: ignore[arg-type]
		input=None,
		parent_id=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
	)
	rs = await run_status_store.get_run(run_id)
	assert rs is not None
	assert rs.state is RunState.RUNNING
	assert rs.task is not None and not rs.task.done()

	fake.finish.set()
	# drain so we don't leak the task
	async for _ in runs_service.subscribe_run_stream(run_id):
		pass
