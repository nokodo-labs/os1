"""integration tests for run lifecycle.

these tests exercise the full service-layer flow:
	launch_thread_run -> spawn background task -> subscribe stream
without going through HTTP, but with the real run registry and stream store,
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
from dataclasses import dataclass, field

import pytest

from api.schemas.runs import RunState
from api.tests.factories import make_principal
from api.v1.service.authentication import Principal
from api.v1.service.runs import failures as run_failures
from api.v1.service.runs import launch as runs_service
from api.v1.service.runs.bus import RunRoute, register_run_route
from api.v1.service.runs.contracts import BUS_UNAVAILABLE_REASON, classify_failure
from api.v1.service.runs.failures import RunFailureReason
from api.v1.service.runs.status import run_registry, run_streams
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, new_typeid


pytestmark = pytest.mark.asyncio

_SUBSCRIBER_ID = TypeID(new_typeid("user"))
"""who these tests attach their streams as."""


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
		run_id_override: TypeID,
		ready_event: asyncio.Event,
		**_kwargs: object,
	) -> object:
		return self._gen(thread_id, agent_id, principal, run_id_override, ready_event)

	async def _gen(
		self,
		thread_id: TypeID,
		agent_id: TypeID,
		principal: object,
		run_id: TypeID,
		ready_event: asyncio.Event,
	) -> None:
		self.run_id = run_id
		await register_run_route(
			run_id,
			RunRoute(
				thread_id=thread_id,
				container_root_id=None,
				agent_id=agent_id,
				user_id=getattr(principal, "user_id", TypeID("test-user")),
				persist=True,
			),
		)
		await run_registry.start_run(
			run_id=run_id,
			thread_id=thread_id,
			agent_id=agent_id,
			user_id=getattr(principal, "user_id", TypeID("test-user")),
		)
		# mirror real run_agent: self-attach the current task so cancel_run
		# works from the very first instant the run is visible.
		current = asyncio.current_task()
		if current is not None:
			await run_registry.attach_task(run_id, current)
		ready_event.set()
		self.started.set()

		# publish an initial frame so subscribers see something on connect
		await self._publish(b'event: delta\ndata: {"i":0}\n\n')

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
						except asyncio.CancelledError, BaseException:
							pass
			if self.finish.is_set():
				break
			self.advance.clear()
			await self._publish(
				f'event: delta\ndata: {{"i":{self.frames_published}}}\n\n'.encode()
			)

		await run_registry.complete_run(run_id)

	async def _publish(self, frame: bytes) -> None:
		assert self.run_id is not None
		await run_streams.publish(self.run_id, frame)
		self.frames_published += 1


@pytest.fixture
def fake_principal() -> Principal:
	return make_principal()


@pytest.fixture
def thread_id() -> TypeID:
	return TypeID(new_typeid("thread"))


@pytest.fixture
def agent_id() -> TypeID:
	return TypeID(new_typeid("agent"))


# ---- tests ---------------------------------------------------------------


async def test_run_outlives_subscriber_disconnect(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""subscriber disconnects mid-run; producer survives; late subscriber catches up."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.launch.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,
		input=None,
		splice=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
		extra_plugins=[],
	)

	# first subscriber gets the initial frame, then disconnects
	stream1 = runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)
	first = await asyncio.wait_for(stream1.__anext__(), timeout=2.0)
	assert b'"i":0' in first
	await stream1.aclose()

	# producer publishes 2 more frames while NOBODY is subscribed
	fake.advance.set()
	# small yield so producer task picks up the advance signal
	await asyncio.sleep(0.05)
	fake.advance.set()
	await asyncio.sleep(0.05)

	# late subscriber connects - must get full catchup (3 frames so far)
	stream2 = runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)
	collected: list[bytes] = []
	for _ in range(3):
		collected.append(await asyncio.wait_for(stream2.__anext__(), timeout=2.0))
	assert any(b'"i":0' in f for f in collected)
	assert any(b'"i":1' in f for f in collected)
	assert any(b'"i":2' in f for f in collected)

	# finish the run cleanly
	fake.finish.set()
	# drain remaining (done sentinel)
	async for _ in stream2:
		pass

	# run is gone
	assert await run_registry.get_run(run_id) is None


async def test_multiple_concurrent_subscribers_get_same_frames(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""two subscribers attached at the same time both observe every live frame."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.launch.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,
		input=None,
		splice=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
		extra_plugins=[],
	)

	stream_a = runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)
	stream_b = runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)

	# both consume the catchup frame (i=0)
	a0 = await asyncio.wait_for(stream_a.__anext__(), timeout=2.0)
	b0 = await asyncio.wait_for(stream_b.__anext__(), timeout=2.0)
	assert a0 == b0

	# advance once - both must observe the new frame
	fake.advance.set()
	a1 = await asyncio.wait_for(stream_a.__anext__(), timeout=2.0)
	b1 = await asyncio.wait_for(stream_b.__anext__(), timeout=2.0)
	assert a1 == b1
	assert b'"i":1' in a1

	fake.finish.set()
	async for _ in stream_a:
		pass
	async for _ in stream_b:
		pass


async def test_cancel_run_terminates_producer_and_unblocks_subscribers(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""cancel_run via the store stops the producer task and ends every stream."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.launch.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,
		input=None,
		splice=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
		extra_plugins=[],
	)

	stream = runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)
	# consume initial frame so the loop is established
	await asyncio.wait_for(stream.__anext__(), timeout=2.0)

	# cancel via the store - simulates POST /threads/{tid}/runs/{rid}/cancel
	cancelled = await run_registry.cancel_run(run_id)
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
	assert await run_registry.get_run(run_id) is None
	# producer task was actually cancelled - state should be FAILED before removal
	# (already removed; we just confirm the in-memory row is gone above)
	# additionally: a fresh cancel returns False
	assert await run_registry.cancel_run(run_id) is False


async def test_late_subscriber_after_eviction_closes_cleanly(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""late subscribers get a terminal done whether or not catchup survives.

	the catchup log persists for a short grace after the producer
	terminates so cross-worker subscribers landing in the
	mark_run_end / LRANGE race window still see the completed stream.
	the log carries an explicit end marker so subscribers detect
	completion without blocking on a pubsub message they missed. past that
	window there is nothing to replay, and the stream still has to close the
	way a completion does: its caller committed the response status line
	before pulling the first frame.
	"""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.launch.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,
		input=None,
		splice=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
		extra_plugins=[],
	)

	# finish immediately and wait for store to clear
	fake.finish.set()
	for _ in range(50):
		if await run_registry.get_run(run_id) is None:
			break
		await asyncio.sleep(0.02)

	# within the catchup grace window: late subscriber drains cleanly
	# (catchup frames + synthesized done, no hang) without UnknownRunError.
	frames = [
		f async for f in runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)
	]
	assert any(b"event: done" in f for f in frames)

	# after the catchup log expires (DELETE the key to simulate post-grace),
	# an unknown run yields a lone done frame rather than raising into a
	# response body that already committed its status line.
	from api.redis import redis_client
	from api.v1.service.runs.bus import _bus, _route_key

	await redis_client.get().delete(_bus._log_key(str(run_id)), _route_key(run_id))

	late = [f async for f in runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)]
	assert late == [sse_encode(event="done", data={})]


async def test_unreachable_bus_ends_the_stream_as_unavailable(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a stream that cannot check the route says "retry", not "we have a bug".

	the status line is already committed, so this has to close like a failure
	rather than raise; and `internal_error` would tell the client to report a
	bug when the honest answer is that a backend was briefly unreachable.
	"""
	from api.v1.service.runs import launch as launch_module
	from api.v1.service.runs.bus import RunBusUnavailableError

	def _unreachable(_run_id: TypeID) -> object:
		raise RunBusUnavailableError("read_run_route")

	monkeypatch.setattr(launch_module, "read_run_route", _unreachable)

	run_id = TypeID(new_typeid("run"))
	frames = [
		f async for f in runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)
	]

	assert any(b'"reason":"unavailable"' in f.replace(b", ", b",") for f in frames)
	assert frames[-1] == sse_encode(event="done", data={})
	# the mechanism stays ours: no frame names the backend that was down.
	assert not any(b"redis" in f.lower() or b"cache" in f.lower() for f in frames)


async def test_steering_attach_outage_is_recorded_as_unavailable(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: Principal,
) -> None:
	"""a steering subscriber that cannot attach is an outage, not a crash.

	it raises after the run is registered, so it would otherwise land in the
	generic handler and persist `internal_error` - telling the user to report
	a bug while the client's own 503 says "try again shortly".
	"""
	from api.v1.service.runs.steering_bus import SteeringUnavailableError

	async def _attach_fails(*_args: object, **_kwargs: object) -> None:
		raise SteeringUnavailableError("run_steering")

	recorded: list[str | None] = []

	async def _capture(_run_id: TypeID, reason: str | None = None) -> None:
		recorded.append(reason)

	monkeypatch.setattr(runs_service, "run_agent", _attach_fails)
	monkeypatch.setattr(runs_service, "terminate_run", _capture)

	run_id = TypeID(new_typeid("run"))
	await runs_service._run_producer(
		run_id=run_id,
		ready_event=asyncio.Event(),
		registered_event=asyncio.Event(),
		outcome=runs_service._StartupOutcome(),
		thread_id=TypeID(new_typeid("thread")),
		agent_id=TypeID(new_typeid("agent")),
		principal=fake_principal,
		input=None,
		splice=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
		extra_plugins=[],
		persist=True,
	)

	assert recorded == [BUS_UNAVAILABLE_REASON]
	assert classify_failure(recorded[0]) is RunFailureReason.UNAVAILABLE


async def test_remote_subscription_waits_when_route_precedes_first_frame(
	fake_principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	run_id = TypeID(new_typeid("run"))
	await register_run_route(
		run_id,
		RunRoute(
			thread_id=thread_id,
			container_root_id=None,
			agent_id=agent_id,
			user_id=fake_principal.user.id,
			persist=True,
		),
	)
	stream = runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID)
	first_frame = asyncio.create_task(anext(stream))
	await asyncio.sleep(0.05)
	assert not first_frame.done()
	frame = b'event: delta\ndata: {"first":true}\n\n'
	from api.v1.service.runs.bus import mirror_frame

	await mirror_frame(run_id, frame)
	assert await asyncio.wait_for(first_frame, timeout=1) == frame
	await stream.aclose()


async def test_state_is_running_while_first_subscriber_attached(
	monkeypatch: pytest.MonkeyPatch,
	fake_principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""sanity: store shows RUNNING state once attach_task completes."""
	fake = _FakeAgent()
	monkeypatch.setattr("api.v1.service.runs.launch.run_agent", fake)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=fake_principal,
		input=None,
		splice=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
		extra_plugins=[],
	)
	rs = await run_registry.get_run(run_id)
	assert rs is not None
	assert rs.state is RunState.RUNNING
	# the producer self-attaches, so the run is cancellable straight away.
	assert await run_registry.cancellation_reason(run_id) is None

	fake.finish.set()
	# drain so we don't leak the task
	async for _ in runs_service.subscribe_run_stream(run_id, _SUBSCRIBER_ID):
		pass


async def test_producer_startup_crash_broadcasts_run_error(
	monkeypatch: pytest.MonkeyPatch,
	thread_id: TypeID,
	agent_id: TypeID,
) -> None:
	"""outer producer failures clear global run state via run.error broadcast."""
	principal = make_principal(slug="startup-crash")
	seen_broadcasts: list[tuple[TypeID, TypeID, TypeID | None, RunFailureReason]] = []

	async def crashing_run_agent(
		thread_id: TypeID,
		agent_id: TypeID,
		principal: Principal,
		run_id_override: TypeID,
		ready_event: asyncio.Event,
		**_kwargs: object,
	) -> None:
		await run_registry.start_run(
			run_id=run_id_override,
			thread_id=thread_id,
			agent_id=agent_id,
			user_id=principal.user.id,
		)
		current = asyncio.current_task()
		if current is not None:
			await run_registry.attach_task(run_id_override, current)
		ready_event.set()
		raise RuntimeError("boom")

	async def fake_broadcast_run_failure(
		thread_id: TypeID,
		agent_id: TypeID,
		reason: RunFailureReason,
		anchor_message_id: TypeID | None = None,
		run_id: TypeID | None = None,
		partial_message_id: TypeID | None = None,
	) -> None:
		seen_broadcasts.append((thread_id, agent_id, run_id, reason))

	monkeypatch.setattr(runs_service, "run_agent", crashing_run_agent)
	# every terminal path now broadcasts through run_failures, so that is where
	# the fanout is intercepted.
	monkeypatch.setattr(
		run_failures, "broadcast_run_failure", fake_broadcast_run_failure
	)

	run_id = await runs_service._start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=principal,
		input=None,
		splice=None,
		client_context=None,
		origin_session_id=None,
		tool_choice=None,
		extra_plugins=[],
	)

	for _attempt in range(50):
		if seen_broadcasts:
			break
		await asyncio.sleep(0.02)

	assert await run_registry.get_run(run_id) is None
	assert seen_broadcasts == [
		(thread_id, agent_id, run_id, RunFailureReason.INTERNAL_ERROR)
	]
