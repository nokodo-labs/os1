"""per-process agent run status store.

tracks active agent runs so any client can discover and resume them
(e.g. on WS connect or page load via the resume SSE endpoint). cross-worker
fanout / cancel / steering goes through redis primitives in the sibling
modules:

- ``run_bus`` mirrors every sse frame to ``nokodo-ai:run:{run_id}:log`` (capped
	list with TTL) and broadcasts on ``nokodo-ai:run:{run_id}:sse`` for late /
  remote subscribers.
- ``steering`` carries per-run user-message injection on
	``nokodo-ai:run:{run_id}:steer`` and drop on ``...:drop``.
- cancel uses a local ``run_id -> Task`` map for instant in-process cancel
  and falls back to a redis control channel publish so the owning worker
  can translate to ``task.cancel()``.

``RunStatus.task`` is a local ``asyncio.Task`` and must not be serialized.
each subscriber keeps a per-process ``set[Queue]``; a single worker-wide
subscriber on each run channel routes received frames into local queues.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from api.database import async_session_local
from api.permissions import ResourceType
from api.v1.service.authorization import list_accessible_user_ids
from api.v1.service.chat import run_bus
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

# stale run TTL - auto-cleanup after this many seconds without updates
_STALE_TTL_SECONDS = 600  # 10 minutes


class RunState(StrEnum):
	"""lifecycle states for an agent run."""

	RUNNING = "running"
	COMPLETED = "completed"
	ERROR = "error"


@dataclass
class RunMessage:
	"""a message emitted during a run (user, assistant, or tool)."""

	message_id: TypeID
	type: str  # "user" | "assistant" | "tool"
	content: list[dict[str, Any]]
	parent_id: TypeID | None = None
	sender_agent_id: TypeID | None = None
	tool_calls: list[dict[str, Any]] = field(default_factory=list)
	created_at: str | None = None


@dataclass
class RunStatus:
	"""snapshot of an active agent run."""

	run_id: TypeID
	agent_id: TypeID
	user_id: TypeID
	thread_id: TypeID | None = None
	state: RunState = RunState.RUNNING

	sse_log: list[bytes] = field(default_factory=list)
	"""accumulated SSE frames for catchup (raw bytes, ready to send).

	unbounded by design: agentic runs may produce thousands of deltas across
	tools, plans, citations, etc. truncating would break catchup for late
	subscribers and hide audit trails. memory pressure is bounded instead by
	the stale-run TTL eviction.
	"""

	messages: list[RunMessage] = field(default_factory=list)
	"""accumulated messages emitted so far (finalized)."""

	streaming_message_id: TypeID | None = None
	"""id of the assistant message currently being streamed, if any."""
	streaming_content: str = ""
	streaming_tool_calls: list[dict[str, Any]] = field(default_factory=list)

	started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

	task: asyncio.Task[object] | None = field(default=None, repr=False)
	"""local producer task driving the agent loop.

	never serialized for cross-worker storage; see module docstring on cancel.
	"""

	steering_inbox: asyncio.Queue[Any] = field(
		default_factory=lambda: asyncio.Queue(maxsize=64),
		repr=False,
	)
	"""bounded queue of pending steering messages to inject into the agent loop.

	items are SDK ``UserMessage`` instances stamped with persistent
	``message_id`` in their ``metadata``. the agent loop drains this between
	iterations via a ``SteeringFilter`` installed on the per-run agent. the
	typed value is
	deliberately ``Any`` so this module does not have to import the SDK.
	capped at 64 to prevent unbounded memory growth from a misbehaving client.
	"""

	pending_steering: list[TypeID] = field(default_factory=list)
	"""message ids for steering messages in flight (still in inbox).

	tracked separately from the SDK queue so terminal handlers can mark
	dropped messages and broadcast ``run.steering.dropped`` without having
	to peek the queue contents.
	"""

	claimed_steering: list[TypeID] = field(default_factory=list)
	"""message ids drained by the SteeringFilter but not yet confirmed
	injected by ``on_injected``.

	keeps in-flight claims visible to terminal handlers: if a run
	terminates between ``claim_pending_steering`` and the filter's
	``on_injected`` callback, the terminal handler sees these ids and
	flips them to dropped (gated by ``only_if_current="queued"`` so a
	successfully-injected message keeps its ``injected`` row).
	"""

	def touch(self) -> None:
		"""update the last-activity timestamp."""
		self.updated_at = datetime.now(tz=UTC)

	def in_flight_steering(self) -> list[TypeID]:
		"""all steering message ids that have not yet been confirmed.

		union of ``pending_steering`` (still in inbox) and
		``claimed_steering`` (drained by the filter but not yet confirmed
		by ``mark_steering_injected``). terminal handlers use this to
		flag every in-flight message as dropped - the conditional
		``only_if_current="queued"`` persist guards against clobbering a
		row that did get successfully injected.
		"""
		return [*self.pending_steering, *self.claimed_steering]

	def to_signal(self) -> dict[str, Any]:
		"""serialize as a lightweight WS signal (same shape as run.started)."""
		return {
			"thread_id": self.thread_id,
			"run_id": self.run_id,
			"agent_id": self.agent_id,
		}


class RunStatusStore:
	"""singleton store for active agent runs.

	thread-safe via asyncio.Lock. keyed by run_id.
	a background cleanup task evicts orphaned runs after _STALE_TTL_SECONDS.
	the cleanup loop starts lazily on first mutation - no external wiring needed.

	## pub/sub

	``publish(run_id, frame)`` records an SSE frame in the run's sse_log and
	pushes it to all active subscribers.

	``subscribe(run_id)`` returns (sse_log, live_queue) so the caller
	can replay recorded frames then await new frames until the run ends.
	terminal signaling is unified: a single ``None`` sentinel ends the live
	queue. callers (subscribe_run_stream) synthesize the SSE ``done`` event
	downstream so we don't carry both a frame and a sentinel.

	this is the mechanism that powers the resume endpoint: any client can
	pick up a run mid-stream and receive full state + live deltas.
	"""

	def __init__(self) -> None:
		self._runs: dict[TypeID, RunStatus] = {}
		self._lock = asyncio.Lock()
		self._cleanup_task: asyncio.Task[None] | None = None
		# subscribers: run_id -> set of asyncio.Queue (one per consumer)
		self._subscribers: dict[TypeID, set[asyncio.Queue[bytes | None]]] = {}

	# --- lifecycle ---

	def _ensure_cleanup_loop(self) -> None:
		"""lazily start the cleanup loop the first time the store is used."""
		if self._cleanup_task is None or self._cleanup_task.done():
			try:
				self._cleanup_task = asyncio.create_task(self._cleanup_loop())
			except RuntimeError:
				# no running event loop yet - will be retried on next call
				pass

	async def _cleanup_loop(self) -> None:
		"""periodically evict stale runs."""
		while True:
			await asyncio.sleep(60)
			now = datetime.now(tz=UTC)
			async with self._lock:
				stale = [
					rid
					for rid, rs in self._runs.items()
					if (now - rs.updated_at).total_seconds() > _STALE_TTL_SECONDS
				]
				for rid in stale:
					logger.info("evicting stale run %s", rid)
					del self._runs[rid]
					self._close_subscribers(rid)

	def _close_subscribers(self, run_id: TypeID) -> None:
		"""send None sentinel to all subscribers and remove them.

		never raises - QueueFull on a saturated subscriber must not crash the
		caller (which is typically complete_run/fail_run/cleanup_loop). a
		subscriber whose queue is full has already received plenty of frames
		and will eventually drain; if it never does, the cleanup loop GC will
		handle it.
		"""
		queues = self._subscribers.pop(run_id, set())
		for q in queues:
			try:
				q.put_nowait(None)
			except asyncio.QueueFull:
				logger.warning(
					"subscriber queue full while closing run %s, skipping sentinel",
					run_id,
				)

	# --- pub/sub ---

	async def publish(self, run_id: TypeID, frame: bytes) -> None:
		"""record an SSE frame and push it to all subscribers."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is not None:
				rs.sse_log.append(frame)
			queues = list(self._subscribers.get(run_id, ()))
		# push outside the lock to minimize contention
		for q in queues:
			try:
				q.put_nowait(frame)
			except asyncio.QueueFull:
				logger.debug("subscriber queue full for run %s, skipping", run_id)
		# cross-worker mirror via redis pub/sub + capped log for catchup.
		await run_bus.mirror_frame(run_id, frame)

	async def subscribe(
		self, run_id: TypeID
	) -> tuple[list[bytes], asyncio.Queue[bytes | None]] | None:
		"""subscribe to a run's SSE stream.

		returns (sse_log, live_queue) or None if the run doesn't exist.
		the caller should:
		1. replay all sse_log frames (catchup)
		2. read from live_queue until None sentinel (run ended)
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return None
			catchup = list(rs.sse_log)
			q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=4096)
			self._subscribers.setdefault(run_id, set()).add(q)
			return catchup, q

	async def unsubscribe(self, run_id: TypeID, q: asyncio.Queue[bytes | None]) -> None:
		"""remove a subscriber queue."""
		async with self._lock:
			subs = self._subscribers.get(run_id)
			if subs is not None:
				subs.discard(q)

	# --- mutations ---

	async def start_run(
		self,
		run_id: TypeID,
		agent_id: TypeID,
		user_id: TypeID,
		thread_id: TypeID | None = None,
	) -> RunStatus:
		"""register a new active run.

		``thread_id`` is optional: ephemeral runs (no DB persistence) still
		register here so they can be cancelled, observed, and broadcast to
		any subscriber. only thread-bound broadcasts (``broadcast_run_event``)
		require a thread_id.
		"""
		self._ensure_cleanup_loop()
		rs = RunStatus(
			run_id=run_id,
			thread_id=thread_id,
			agent_id=agent_id,
			user_id=user_id,
			state=RunState.RUNNING,
		)
		async with self._lock:
			self._runs[run_id] = rs
		return rs

	async def attach_task(self, run_id: TypeID, task: asyncio.Task[object]) -> None:
		"""attach the producer task to a run for cancel support."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is not None:
				rs.task = task

	async def cancel_run(self, run_id: TypeID) -> bool:
		"""cancel a run's producer task. returns True if a task was cancelled.

		the task's cancellation handler is responsible for calling fail_run and
		broadcasting run.completed to clients. this method only triggers the
		cancellation - it does NOT remove the run from the store directly.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			task = rs.task if rs is not None else None
		if task is not None and not task.done():
			task.cancel()
			return True
		return False

	async def enqueue_steering(
		self,
		run_id: TypeID,
		message_id: TypeID,
		sdk_user_message: Any,
	) -> bool:
		"""enqueue a steering message for in-flight injection.

		returns True if the run is alive and accepted the message, False if
		the run is unknown, terminal, or the inbox is full. the agent loop
		drains the inbox between iterations via a ``SteeringFilter`` on the
		per-run agent.

		the ``put`` is performed under the lock so that a concurrent
		``claim_pending_steering`` cannot race past the put and leave a
		stranded message in the inbox after the pending list has been
		cleared.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None or rs.state != RunState.RUNNING:
				return False
			if rs.steering_inbox.full():
				return False
			rs.pending_steering.append(message_id)
			rs.steering_inbox.put_nowait(sdk_user_message)
			rs.touch()
		return True

	async def mark_steering_injected(
		self, run_id: TypeID, message_ids: list[TypeID]
	) -> None:
		"""confirm in-flight claims as injected.

		called from the ``SteeringFilter.on_injected`` callback once the
		messages have been drained onto the thread. removes from BOTH
		``pending_steering`` (defensive - normally already moved by claim)
		and ``claimed_steering`` so terminal handlers no longer see them
		as in-flight. no-op for unknown runs or empty input.
		"""
		if not message_ids:
			return
		injected = set(message_ids)
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			rs.pending_steering = [
				mid for mid in rs.pending_steering if mid not in injected
			]
			rs.claimed_steering = [
				mid for mid in rs.claimed_steering if mid not in injected
			]
			rs.touch()

	async def claim_pending_steering(self, run_id: TypeID) -> list[Any]:
		"""atomically drain queued steering messages for in-line injection.

		drains both ``steering_inbox`` and ``pending_steering`` under the
		store lock so a concurrent ``drop_pending_steering`` either sees
		the messages still pending (drop wins, filter gets nothing) or
		sees an empty pending list (claim wins, drop is a no-op). this
		eliminates the race where the SDK filter would inject a message
		into the thread while a drop request flagged the same row dropped
		in the DB.

		message ids are MOVED from ``pending_steering`` into
		``claimed_steering`` (rather than just cleared) so terminal
		handlers landing during the brief window before
		``mark_steering_injected`` confirms them still see them as
		in-flight and can flip them to dropped.

		callers (the SteeringFilter) treat the returned list as
		"definitively going into the thread" and MUST follow up with
		``mark_steering_injected`` once the on_injected callback completes.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return []
			drained: list[Any] = []
			while True:
				try:
					drained.append(rs.steering_inbox.get_nowait())
				except asyncio.QueueEmpty:
					break
			if drained:
				# the inbox and pending_steering are kept in lockstep by
				# enqueue_steering, so everything drained corresponds to a
				# pending entry. move them into the claimed bucket.
				rs.claimed_steering.extend(rs.pending_steering)
				rs.pending_steering.clear()
				rs.touch()
			return drained

	async def drop_pending_steering(self, run_id: TypeID, message_id: TypeID) -> bool:
		"""remove a still-queued steering message before the agent drains it.

		returns True if the message was found and removed from both the
		pending list and the SDK inbox; False if the message was unknown
		(already injected, already dropped, or never queued here).

		the inbox queue is rebuilt under the lock so the agent loop's
		``get_nowait`` drain is naturally consistent: it sees either the
		message (if drop loses the race) or no message (if drop wins).
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return False
			idx = next(
				(i for i, mid in enumerate(rs.pending_steering) if mid == message_id),
				-1,
			)
			if idx == -1:
				return False
			# drain the parallel inbox, drop the matching position, refill.
			# pending_steering and steering_inbox are kept in lockstep by
			# enqueue_steering (both append under the same lock).
			drained: list[Any] = []
			while True:
				try:
					drained.append(rs.steering_inbox.get_nowait())
				except asyncio.QueueEmpty:
					break
			rs.pending_steering.pop(idx)
			# best-effort positional drop: if lengths diverge (shouldn't, but
			# defensive) we just refill everything and let metadata flip on
			# the dropped message handle the UI.
			if 0 <= idx < len(drained):
				drained.pop(idx)
			for item in drained:
				try:
					rs.steering_inbox.put_nowait(item)
				except asyncio.QueueFull:
					# extremely unlikely (we just made room), but if so,
					# we lose the tail; surfaces as additional dropped
					# messages on the next drain cycle.
					logger.warning("inbox refill overflow on drop for run %s", run_id)
					break
			rs.touch()
		return True

	async def add_message(
		self,
		run_id: TypeID,
		message_id: TypeID,
		message_type: str,
		content: list[dict[str, Any]],
		parent_id: TypeID | None = None,
		sender_agent_id: TypeID | None = None,
		tool_calls: list[dict[str, Any]] | None = None,
		created_at: str | None = None,
	) -> None:
		"""record a finalized message in the run."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			rs.messages.append(
				RunMessage(
					message_id=message_id,
					type=message_type,
					content=content,
					parent_id=parent_id,
					sender_agent_id=sender_agent_id,
					tool_calls=tool_calls or [],
					created_at=created_at,
				)
			)
			# clear streaming state when a message finalizes
			if rs.streaming_message_id == message_id:
				rs.streaming_message_id = None
				rs.streaming_content = ""
				rs.streaming_tool_calls = []
			rs.touch()

	async def update_streaming(
		self,
		run_id: TypeID,
		message_id: TypeID,
		content: str,
		tool_calls: list[dict[str, Any]] | None = None,
	) -> None:
		"""update the in-progress streaming assistant content."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			rs.streaming_message_id = message_id
			rs.streaming_content = content
			if tool_calls is not None:
				rs.streaming_tool_calls = tool_calls
			rs.touch()

	async def complete_run(self, run_id: TypeID) -> RunStatus | None:
		"""mark a run as completed and close subscribers.

		only the ``None`` sentinel is delivered; subscribe_run_stream synthesizes
		the terminal SSE ``done`` event so we don't double-signal.
		"""
		async with self._lock:
			rs = self._runs.pop(run_id, None)
			if rs is not None:
				rs.state = RunState.COMPLETED
				rs.touch()
			# snapshot under the lock to match fail_run's pattern and avoid
			# racing with subscribe / unsubscribe / cleanup_loop.
			subscribers = list(self._subscribers.get(run_id, ()))
			self._subscribers.pop(run_id, None)
		if rs is not None:
			for q in subscribers:
				try:
					q.put_nowait(None)
				except asyncio.QueueFull:
					# best-effort close; subscribers with full queues will
					# notice the run is gone via the next get + lookup.
					pass
			# tell remote subscribers (other workers) that the stream is
			# done, then mark the catchup log for short-grace expiry.
			# cleanup_run_log uses EXPIRE rather than DELETE so a late
			# cross-worker subscriber landing within the grace window still
			# sees the catchup; subsequent subscribers see the key expired
			# and get UnknownRunError.
			await run_bus.mark_run_end(run_id)
			await run_bus.cleanup_run_log(run_id)
		return rs

	async def fail_run(
		self,
		run_id: TypeID,
		reason: str | None = None,
	) -> RunStatus | None:
		"""mark a run as errored, push the error frame, and close subscribers.

		the error frame carries ``run_id`` and an optional human-readable
		``reason`` so subscribers can correlate it with the active run and
		display something meaningful. the terminal ``done`` event is
		synthesized by subscribe_run_stream from the ``None`` sentinel.

		idempotent: if the run is already gone (e.g. concurrent fail/complete)
		this returns ``None`` and is otherwise a no-op.
		"""
		async with self._lock:
			rs = self._runs.pop(run_id, None)
			if rs is None:
				return None
			# snapshot subscribers under the lock so a concurrent unsubscribe
			# or _close_subscribers (e.g. from cleanup_loop) can't yank the set
			# out from under us between the pop and the push. clear the
			# subscriber set in the same critical section so the post-lock
			# close pass is purely best-effort sentinel delivery.
			subscribers = list(self._subscribers.get(run_id, ()))
			self._subscribers.pop(run_id, None)
		err_payload: dict[str, Any] = {
			"run_id": str(run_id),
			"message": reason or "generation failed",
		}
		if reason is not None:
			err_payload["reason"] = reason
		err_frame = sse_encode(event="error", data=err_payload)
		# also append to the in-memory log so any catchup-only late subscriber
		# (race: arrives between pop and the catchup snapshot) still sees the
		# error reason rather than just a bare done sentinel.
		rs.sse_log.append(err_frame)
		# mirror the error frame to redis so cross-worker late subscribers
		# see the failure reason via the catchup LRANGE; without this they
		# only see the end sentinel and lose the failure context.
		await run_bus.mirror_frame(run_id, err_frame)
		for q in subscribers:
			try:
				q.put_nowait(err_frame)
			except asyncio.QueueFull:
				logger.warning(
					"subscriber queue full while failing run %s, dropping error",
					run_id,
				)
			# deliver the close sentinel directly to each subscriber rather
			# than re-resolving via _close_subscribers (the set is already
			# cleared under the lock above).
			try:
				q.put_nowait(None)
			except asyncio.QueueFull:
				pass
		# tell remote subscribers the stream ended; cleanup_run_log uses
		# a short EXPIRE so late cross-worker subscribers within the grace
		# window still get the catchup + the mirrored error frame.
		await run_bus.mark_run_end(run_id)
		await run_bus.cleanup_run_log(run_id)
		return rs

	# --- queries ---

	async def get_run(self, run_id: TypeID) -> RunStatus | None:
		"""get a single run by ID."""
		async with self._lock:
			return self._runs.get(run_id)

	async def has_in_flight_steering(self, run_id: TypeID) -> bool:
		"""return whether a running API run still has steering to settle."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None or rs.state != RunState.RUNNING:
				return False
			return bool(
				rs.pending_steering
				or rs.claimed_steering
				or not rs.steering_inbox.empty()
			)

	async def get_active_runs_for_thread(self, thread_id: TypeID) -> list[RunStatus]:
		"""get all active runs for a given thread."""
		async with self._lock:
			return [
				rs
				for rs in self._runs.values()
				if rs.thread_id == thread_id and rs.state == RunState.RUNNING
			]

	async def get_active_runs_for_threads(
		self, thread_ids: list[TypeID]
	) -> list[RunStatus]:
		"""get all active runs across multiple threads."""
		tid_set = set(thread_ids)
		async with self._lock:
			return [
				rs
				for rs in self._runs.values()
				if rs.thread_id in tid_set and rs.state == RunState.RUNNING
			]

	async def get_all_active_runs(self) -> list[RunStatus]:
		"""get all currently active runs across all threads."""
		async with self._lock:
			return [rs for rs in self._runs.values() if rs.state == RunState.RUNNING]

	async def get_runs_for_user(self, user_id: TypeID) -> list[RunStatus]:
		"""get all active runs owned by a specific user."""
		async with self._lock:
			return [
				rs
				for rs in self._runs.values()
				if rs.user_id == user_id and rs.state == RunState.RUNNING
			]


# module-level singleton
run_status_store = RunStatusStore()


async def get_active_runs_signal(user_id: TypeID) -> dict[str, Any]:
	"""build a single WS signal listing active agent runs for the user.

	returns a ready-to-send dict ``{type: 'runs.active', data: [...]}``.
	an empty ``data`` list is meaningful: it tells the client to clear any
	stale active-run pointers from a previous connection. this is NOT catchup
	data - it's a lightweight pointer list so the client knows which runs to
	resume via the SSE endpoint.
	"""
	# collect thread IDs from all currently active runs
	all_runs = await run_status_store.get_all_active_runs()
	if not all_runs:
		return {"type": "runs.active", "data": []}

	unique_thread_ids = {rs.thread_id for rs in all_runs if rs.thread_id is not None}

	# resolve which of those threads the user can access
	accessible_threads: set[TypeID] = set()
	async with async_session_local() as db_session:
		for tid in unique_thread_ids:
			user_ids = await list_accessible_user_ids(
				ResourceType.THREAD, tid, db_session
			)
			if user_id in user_ids:
				accessible_threads.add(tid)

	matching_runs = [
		rs
		for rs in all_runs
		if rs.thread_id is not None and rs.thread_id in accessible_threads
	]
	if not matching_runs:
		return {"type": "runs.active", "data": []}

	return {
		"type": "runs.active",
		"data": [rs.to_signal() for rs in matching_runs],
	}
