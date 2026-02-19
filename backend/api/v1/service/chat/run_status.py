"""in-memory agent run status store.

tracks active agent runs so any client can discover and resume active runs
(e.g. on WS connect or page load via the resume SSE endpoint).

## redis migration notes

this module is a self-contained singleton designed for easy swap to Redis:
- replace ``_runs`` dict with Redis hash/json (key per run_id)
- replace ``_subscribers`` dict with Redis Pub/Sub channels (per run_id)
- replace ``_lock`` with Redis distributed lock (or remove if using Redis atomics)
- ``subscribe()`` becomes ``SUBSCRIBE run:{run_id}`` + async iteration
- ``publish()`` becomes ``PUBLISH run:{run_id} <frame>``
- cleanup loop becomes Redis key TTL (no background task needed)
- ``get_active_runs_for_thread(s)`` becomes a secondary index or scan

the public API (start_run, add_message, update_streaming, complete_run,
fail_run, subscribe, publish, get_*) should stay identical.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from api.core.database import AsyncSessionLocal
from api.permissions import ResourceType
from api.v1.service.authorization import list_accessible_user_ids
from nokodo_ai.utils.sse import sse_encode


logger = logging.getLogger(__name__)

# stale run TTL — auto-cleanup after this many seconds without updates
_STALE_TTL_SECONDS = 600  # 10 minutes


class RunState(StrEnum):
	"""lifecycle states for an agent run."""

	RUNNING = "running"
	COMPLETED = "completed"
	ERROR = "error"


@dataclass
class RunMessage:
	"""a message emitted during a run (user, assistant, or tool)."""

	message_id: str
	type: str  # "user" | "assistant" | "tool"
	content: list[dict[str, Any]]
	parent_id: str | None = None
	sender_agent_id: str | None = None
	tool_calls: list[dict[str, Any]] = field(default_factory=list)
	created_at: str | None = None


@dataclass
class RunStatus:
	"""snapshot of an active agent run."""

	run_id: str
	thread_id: str
	agent_id: str
	user_id: str
	state: RunState = RunState.RUNNING

	# accumulated SSE frames for catchup (raw bytes, ready to send)
	sse_log: list[bytes] = field(default_factory=list)

	# accumulated messages emitted so far (finalized)
	messages: list[RunMessage] = field(default_factory=list)

	# current streaming assistant content (partial, still being generated)
	streaming_message_id: str | None = None
	streaming_content: str = ""
	streaming_tool_calls: list[dict[str, Any]] = field(default_factory=list)

	started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

	def touch(self) -> None:
		"""update the last-activity timestamp."""
		self.updated_at = datetime.now(tz=UTC)

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
	the cleanup loop starts lazily on first mutation — no external wiring needed.

	## pub/sub

	``publish(run_id, frame)`` records an SSE frame in the run's sse_log and
	pushes it to all active subscribers.

	``subscribe(run_id)`` returns (sse_log, live_queue) so the caller
	can replay recorded frames then await new frames until the run ends (None sentinel).

	this is the mechanism that powers the resume endpoint: any client can
	pick up a run mid-stream and receive full state + live deltas.
	"""

	def __init__(self) -> None:
		self._runs: dict[str, RunStatus] = {}
		self._lock = asyncio.Lock()
		self._cleanup_task: asyncio.Task[None] | None = None
		# subscribers: run_id → set of asyncio.Queue (one per consumer)
		self._subscribers: dict[str, set[asyncio.Queue[bytes | None]]] = {}

	# --- lifecycle ---

	def _ensure_cleanup_loop(self) -> None:
		"""lazily start the cleanup loop the first time the store is used."""
		if self._cleanup_task is None or self._cleanup_task.done():
			try:
				self._cleanup_task = asyncio.create_task(self._cleanup_loop())
			except RuntimeError:
				# no running event loop yet — will be retried on next call
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

	def _close_subscribers(self, run_id: str) -> None:
		"""send None sentinel to all subscribers and remove them."""
		queues = self._subscribers.pop(run_id, set())
		for q in queues:
			q.put_nowait(None)

	# --- pub/sub ---

	async def publish(self, run_id: str, frame: bytes) -> None:
		"""record an SSE frame and push it to all subscribers."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is not None:
				rs.sse_log.append(frame)
			for q in self._subscribers.get(run_id, set()):
				try:
					q.put_nowait(frame)
				except asyncio.QueueFull:
					logger.debug("subscriber queue full for run %s, skipping", run_id)

	async def subscribe(
		self, run_id: str
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

	async def unsubscribe(self, run_id: str, q: asyncio.Queue[bytes | None]) -> None:
		"""remove a subscriber queue."""
		async with self._lock:
			subs = self._subscribers.get(run_id)
			if subs is not None:
				subs.discard(q)

	# --- mutations ---

	async def start_run(
		self,
		*,
		run_id: str,
		thread_id: str,
		agent_id: str,
		user_id: str,
	) -> RunStatus:
		"""register a new active run."""
		self._ensure_cleanup_loop()
		rs = RunStatus(
			run_id=run_id,
			thread_id=thread_id,
			agent_id=str(agent_id),
			user_id=user_id,
			state=RunState.RUNNING,
		)
		async with self._lock:
			self._runs[run_id] = rs
		return rs

	async def add_message(
		self,
		run_id: str,
		*,
		message_id: str,
		message_type: str,
		content: list[dict[str, Any]],
		parent_id: str | None = None,
		sender_agent_id: str | None = None,
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
		run_id: str,
		*,
		message_id: str,
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

	async def complete_run(self, run_id: str) -> RunStatus | None:
		"""mark a run as completed, notify subscribers, and remove it."""
		async with self._lock:
			rs = self._runs.pop(run_id, None)
			if rs is not None:
				rs.state = RunState.COMPLETED
				rs.touch()
		# send done sentinel outside the lock
		if rs is not None:
			done_frame = sse_encode(event="done", data={})
			for q in self._subscribers.get(run_id, set()):
				try:
					q.put_nowait(done_frame)
				except asyncio.QueueFull:
					pass
			self._close_subscribers(run_id)
		return rs

	async def fail_run(self, run_id: str) -> RunStatus | None:
		"""mark a run as errored, notify subscribers, and remove it."""
		async with self._lock:
			rs = self._runs.pop(run_id, None)
			if rs is not None:
				rs.state = RunState.ERROR
				rs.touch()
		# send error + done sentinel outside the lock
		if rs is not None:
			err_frame = sse_encode(event="error", data={"message": "generation failed"})
			done_frame = sse_encode(event="done", data={})
			for q in self._subscribers.get(run_id, set()):
				try:
					q.put_nowait(err_frame)
					q.put_nowait(done_frame)
				except asyncio.QueueFull:
					pass
			self._close_subscribers(run_id)
		return rs

	# --- queries ---

	async def get_run(self, run_id: str) -> RunStatus | None:
		"""get a single run by ID."""
		async with self._lock:
			return self._runs.get(run_id)

	async def get_active_runs_for_thread(self, thread_id: str) -> list[RunStatus]:
		"""get all active runs for a given thread."""
		async with self._lock:
			return [
				rs
				for rs in self._runs.values()
				if rs.thread_id == thread_id and rs.state == RunState.RUNNING
			]

	async def get_active_runs_for_threads(
		self, thread_ids: list[str]
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

	async def get_runs_for_user(self, user_id: str) -> list[RunStatus]:
		"""get all active runs owned by a specific user."""
		async with self._lock:
			return [
				rs
				for rs in self._runs.values()
				if rs.user_id == user_id and rs.state == RunState.RUNNING
			]


# module-level singleton
run_status_store = RunStatusStore()


async def get_active_runs_signal(user_id: str) -> dict[str, Any] | None:
	"""build a single WS signal listing active agent runs for the user.

	returns a ready-to-send dict ``{type: 'runs.active', data: [...]}``
	or None if there are no active runs.  this is NOT catchup data — it's
	a lightweight pointer list so the client knows which runs to resume
	via the SSE endpoint.
	"""
	# collect thread IDs from all currently active runs
	all_runs = await run_status_store.get_all_active_runs()
	if not all_runs:
		return None

	unique_thread_ids = {rs.thread_id for rs in all_runs}

	# resolve which of those threads the user can access
	accessible_threads: set[str] = set()
	async with AsyncSessionLocal() as db_session:
		for tid in unique_thread_ids:
			user_ids = await list_accessible_user_ids(
				ResourceType.THREAD, tid, db_session
			)
			if user_id in user_ids:
				accessible_threads.add(tid)

	matching_runs = [rs for rs in all_runs if rs.thread_id in accessible_threads]
	if not matching_runs:
		return None

	return {
		"type": "runs.active",
		"data": [rs.to_signal() for rs in matching_runs],
	}
