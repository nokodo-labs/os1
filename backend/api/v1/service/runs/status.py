"""per-process run state with Redis-mirrored SSE resume frames."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Literal, Protocol, TypedDict

from sqlalchemy import select

from api.database import async_session_local
from api.models.access_rule import AccessLevel
from api.models.event_types import EventType
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.runs import RunState
from api.v1.service.authentication import load_principal_for_user
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.events import broadcast_to_resource
from api.v1.service.runs.bus import (
	PENDING_RUN_SLOT_TTL_SECONDS,
	RUN_LOG_MAX_FRAMES,
	RunSlotActive,
	RunSlotPending,
	abandon_run_slot,
	best_effort_teardown,
	claim_run_slot,
	cleanup_run_log,
	mark_run_end,
	mirror_frame,
	mirror_frames,
	promote_run_slot,
	refresh_run_slot,
	release_run_slot,
	wait_run_slot,
)
from api.v1.service.runs.contracts import (
	SteeringInjection,
	classify_failure,
	same_container,
)
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)


class ActiveRunSignal(TypedDict):
	"""one active run, as a client needs to find and resume it."""

	thread_id: TypeID | None
	"""conversation the run answers in; None for an ephemeral run."""
	run_id: TypeID
	"""the run to resume."""
	agent_id: TypeID
	"""the agent answering."""


class ActiveRunsSignal(TypedDict):
	"""the full set of runs a reconnecting client should know about."""

	type: Literal["runs.active"]
	"""discriminator clients switch on."""
	data: list[ActiveRunSignal]
	"""every run this user can see; empty clears their stale pointers."""


_STALE_TTL_SECONDS = 600
"""how long a run may go without publishing before it is presumed wedged.

publishing is the heartbeat, so this only elapses for a run that has stopped
producing entirely - not one that is merely slow between deltas.
"""

_SLOT_TIMEOUT_SECONDS = PENDING_RUN_SLOT_TTL_SECONDS
"""how long an agent slot may stay unresolved before it is abandoned.

the same bound governs waiters and cleanup, so a caller never gives up while the
store still considers the slot healthy.
"""

_MAX_INBOX = 64
"""how many undelivered injections a run will hold before refusing more."""


async def broadcast_run_event(
	thread_id: TypeID,
	agent_id: TypeID,
	run_id: TypeID,
	started: bool,
) -> None:
	"""broadcast run.started / run.completed to all users with access.

	live-only, and rightly so: these say a run began or ended cleanly, which is
	transient status. the run's OUTCOMES - its messages, and its failure - are
	what persists. see ``broadcast_run_failure``.
	"""
	msg_type = EventType.RUN_STARTED if started else EventType.RUN_COMPLETED
	await broadcast_to_resource(
		ResourceType.THREAD,
		thread_id,
		{
			"type": msg_type,
			"data": {
				"thread_id": thread_id,
				"agent_id": agent_id,
				"run_id": run_id,
			},
		},
	)


@dataclass(slots=True)
class AgentSlot:
	"""a run being started for one agent in one conversation.

	held from the moment a caller decides to start a run until that run is
	registered, which is the window where a second invocation would otherwise
	see no active run and start a duplicate.
	"""

	ready: asyncio.Event
	"""set once the slot resolves, releasing everyone waiting on it."""
	claimed_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	"""when the slot was taken, which is what makes it expirable."""
	run_id: TypeID | None = None
	"""the run that was started; None once the start failed."""
	distributed_key: str | None = None
	"""the cross-worker slot key, when this claim reached Redis."""
	distributed_token: str | None = None
	"""proves this worker still owns the distributed slot it claimed."""


@dataclass(frozen=True, slots=True)
class SteerExistingRun:
	"""a run is already answering here; hand it the message."""

	run_id: TypeID
	"""the run to steer instead of starting another."""


@dataclass(frozen=True, slots=True)
class StartNewRun:
	"""nobody is answering; this caller starts the run and releases the slot."""

	slot: AgentSlot
	"""the claim this caller must release once its run is registered."""


@dataclass(frozen=True, slots=True)
class AwaitPendingRun:
	"""another caller is mid-start; wait for its run, then steer that."""

	slot: AgentSlot
	"""the in-flight claim to wait on for its run id."""


type AgentSlotClaim = SteerExistingRun | StartNewRun | AwaitPendingRun
"""what an invoking caller should do about an agent's slot.

exactly one of three things is true, so this is a union rather than one record
with three nullable fields - the caller matches on the case instead of rebuilding
it from which field happens to be set.
"""


@dataclass(frozen=True, slots=True)
class CatchUpReserved:
	"""a mention's catch-up range, claimed."""

	invocation_message_id: TypeID
	"""invocation this reservation claimed the cursor for."""
	previous_invocation_id: TypeID | None
	"""invocation the reserved segment starts after; the caller restores it if
	the batch never reaches the run."""


@dataclass(frozen=True, slots=True)
class CatchUpRefused:
	"""the run cannot take this catch-up because it is gone or full."""


@dataclass(frozen=True, slots=True)
class CatchUpAlreadyAccepted:
	"""the run already accepted this invocation boundary."""


type CatchUpReservation = CatchUpReserved | CatchUpRefused | CatchUpAlreadyAccepted
"""what the store decided about one mention's catch-up claim.

refusal and already-accepted are different outcomes: the first owes the caller
a dropped resolution, the second is already someone else's to deliver.
"""


@dataclass(frozen=True, slots=True)
class ReplyAnchorReservation:
	"""one answer's claim on a pending reply anchor."""

	token: str
	"""identifies this claim, so a stale holder cannot settle a newer one."""
	message_id: TypeID
	"""the invocation this answer will reply to."""


class Injection(SteeringInjection, Protocol):
	"""one unit of conversation waiting to enter a run.

	extends what the filter consumes (``messages``) with what only the store
	needs: an id to drop one by, and whether an undelivered one leaves a
	persisted row owing a resolution. what each unit MEANS stays with the
	caller.
	"""

	@property
	def message_id(self) -> TypeID:
		"""identifies this injection in the inbox."""
		...

	@property
	def retractable(self) -> bool:
		"""whether a run that dies owing this must retract a persisted row."""
		...


@dataclass
class RunStatus:
	"""the store's live record of one active agent run."""

	run_id: TypeID
	"""identifies the run everywhere, including across workers."""
	agent_id: TypeID
	"""the agent doing the answering."""
	user_id: TypeID
	"""who started the run, and who owns it when there is no thread."""
	thread_id: TypeID | None = None
	"""conversation being answered; None for an ephemeral run."""
	state: RunState = RunState.RUNNING
	"""lifecycle state; terminal only on the snapshot a caller is handed."""
	persist: bool = True
	"""whether this run's outputs are written down."""

	container_root_id: TypeID | None = None
	"""sub-thread this run answers in; None for the canon conversation.

	together with thread and agent it identifies the conversation whose mentions
	steer this run, so a nested sub-thread never catches up a canon run.
	"""
	conversation_bound: bool = False
	"""whether container_root_id identifies a resolved conversation.

	None means canon only after this becomes true; before that, the run must not
	claim invocations from any container.
	"""

	queued_through_message_id: TypeID | None = None
	"""newest invocation whose catch-up this run has accepted.

	reserved at enqueue rather than at injection so two overlapping mentions
	queue disjoint segments instead of the same messages twice.
	"""

	injected_through_message_id: TypeID | None = None
	"""newest invocation actually delivered into the agent's thread."""

	anchor_message_id: TypeID | None = None
	"""where this run renders in the conversation.

	separate from the boundaries above, which say what the agent has READ: a
	run that fails before reading anything still happened somewhere, and the
	only participant-facing event read path is keyed by message id, so an
	unanchored failure is invisible on reload.
	"""

	reply_anchor_message_id: TypeID | None = None
	"""invocation the run's next visible answer replies to."""

	reply_anchor_pending: bool = False
	"""whether the current anchor is still waiting for its first answer."""

	reply_anchor_claim_token: str | None = None
	"""claim held by an accepted output command until its row commits."""

	cancellation_reason: str | None = None
	"""terminal reason requested by the run's cancellation owner."""

	sse_log: list[bytes] = field(default_factory=list)
	"""accumulated SSE frames for catchup (raw bytes, ready to send).

	bounded to the same newest-frame window as Redis so local and remote resume
	have one catchup contract.
	"""
	sse_truncated: bool = False
	"""whether older catchup frames fell outside the retained window."""

	started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	"""when the run was registered."""
	updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	"""last sign of life; the cleanup loop evicts on this."""

	task: asyncio.Task[object] | None = field(default=None, repr=False)
	"""local producer task driving the agent loop.

	never serialized for cross-worker storage; see module docstring on cancel.
	"""
	steering_task: asyncio.Task[object] | None = field(default=None, repr=False)
	"""local Redis command subscriber owned by this run lifecycle."""

	steering_inbox: list[Injection] = field(default_factory=list)
	"""injections waiting to be drained into the agent loop.

	a list rather than a queue because every drain takes the whole thing: the
	filter claims at an iteration boundary and injects the batch in order.
	capped at ``_MAX_INBOX`` to bound memory from a misbehaving client.
	"""

	claimed_steering: list[TypeID] = field(default_factory=list)
	"""queued-steering ids drained by the filter but not yet confirmed
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
		"""queued-steering ids that still owe the user a resolution.

		ONLY queued steering: it is persisted as a ghost row before the agent
		has read it, so a run that dies owing one must flip it to dropped. an
		invocation catch-up writes nothing - its only residue is a cursor,
		which ``release_catch_up`` owns - so it never belongs here.
		"""
		return [
			injection.message_id
			for injection in self.steering_inbox
			if injection.retractable
		] + list(self.claimed_steering)

	def to_signal(self) -> ActiveRunSignal:
		"""serialize as a lightweight WS signal (same shape as run.started)."""
		return {
			"thread_id": self.thread_id,
			"run_id": self.run_id,
			"agent_id": self.agent_id,
		}

	def snapshot(self) -> RunSnapshot:
		"""copy this run's state for a reader outside the store."""
		return RunSnapshot(
			run_id=self.run_id,
			agent_id=self.agent_id,
			user_id=self.user_id,
			thread_id=self.thread_id,
			state=self.state,
			persist=self.persist,
			container_root_id=self.container_root_id,
			conversation_bound=self.conversation_bound,
			queued_through_message_id=self.queued_through_message_id,
			injected_through_message_id=self.injected_through_message_id,
			anchor_message_id=self.anchor_message_id,
			started_at=self.started_at,
			updated_at=self.updated_at,
			inbox_message_ids=tuple(
				injection.message_id for injection in self.steering_inbox
			),
			claimed_steering=tuple(self.claimed_steering),
			in_flight_steering=tuple(self.in_flight_steering()),
		)


@dataclass(frozen=True, slots=True)
class RunSnapshot:
	"""one run's state as of the moment a reader asked for it.

	the store guards its map with a lock, which says nothing about what a
	caller does with a record after taking it - so readers get a copy and the
	live record never leaves the store. every mutation goes through a store
	method, which is where the lock actually applies.
	"""

	run_id: TypeID
	"""identifies the run this was taken from."""
	agent_id: TypeID
	"""the agent doing the answering."""
	user_id: TypeID
	"""who started the run, and who owns it when there is no thread."""
	thread_id: TypeID | None
	"""conversation being answered; None for an ephemeral run."""
	state: RunState
	"""lifecycle state at the moment the snapshot was taken."""
	persist: bool
	"""whether this run's outputs are written down."""
	container_root_id: TypeID | None
	"""sub-thread the run answers in; None for the canon conversation."""
	conversation_bound: bool
	"""whether the run knows which conversation it answers yet."""
	queued_through_message_id: TypeID | None
	"""newest invocation whose catch-up the run has accepted."""
	injected_through_message_id: TypeID | None
	"""newest invocation actually delivered into the agent's thread."""
	anchor_message_id: TypeID | None
	"""where this run renders, which is where a failure would be recorded."""
	started_at: datetime
	"""when the run was registered."""
	updated_at: datetime
	"""last sign of life at snapshot time."""
	inbox_message_ids: tuple[TypeID, ...]
	"""what the run's inbox was holding, undelivered."""
	claimed_steering: tuple[TypeID, ...]
	"""steering the filter drained but has not confirmed injected."""
	in_flight_steering: tuple[TypeID, ...]
	"""steering ids that still owe the user a resolution if the run dies."""

	def to_signal(self) -> ActiveRunSignal:
		"""serialize as a lightweight WS signal (same shape as run.started)."""
		return {
			"thread_id": self.thread_id,
			"run_id": self.run_id,
			"agent_id": self.agent_id,
		}


class RunStore:
	"""shared state behind the run lifecycle, stream, conversation, and inbox stores.

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
		"""start an empty store; the cleanup loop begins on first use."""
		self._runs: dict[TypeID, RunStatus] = {}
		self._lock = asyncio.Lock()
		"""guards every field below. no critical section may await.

		load-bearing, not stylistic: a fully synchronous critical section means
		a caller either sees the state before a mutation or after it, never
		mid-way, so readers can hand out snapshots without copying under a
		second lock. an await inside would also let a mutation interleave with
		its own precondition check - which is exactly what the slot claim and
		catch-up reservation exist to prevent.
		"""
		self._cleanup_task: asyncio.Task[None] | None = None
		# subscribers: run_id -> {queue: the user it was authorized as}
		self._subscribers: dict[TypeID, dict[asyncio.Queue[bytes | None], TypeID]] = {}
		self._mirror_queues: dict[TypeID, asyncio.Queue[bytes]] = {}
		self._mirror_tasks: dict[TypeID, asyncio.Task[None]] = {}
		# agent slots being started: (thread, container, agent) -> slot
		self._agent_slots: dict[tuple[str, str, str], AgentSlot] = {}
		self._agent_slot_claim_lock = asyncio.Lock()
		self._on_stale_run: Callable[[TypeID], Awaitable[None]] | None = None

	def on_stale_run(self, handler: Callable[[TypeID], Awaitable[None]]) -> None:
		"""register how an evicted run is ended.

		the store cannot broadcast or write failure records itself - those live
		a layer up and import it - so the owner supplies the terminal path.
		"""
		self._on_stale_run = handler

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
		"""periodically evict stale runs and abandoned agent slots."""
		while True:
			await asyncio.sleep(_SLOT_TIMEOUT_SECONDS)
			try:
				await self._cleanup_stale_state()
			except Exception:
				logger.exception("run state cleanup iteration failed")

	async def _cleanup_stale_state(self) -> None:
		"""evict stale runs and abandoned startup slots once."""
		now = datetime.now(tz=UTC)
		abandoned_slots: list[AgentSlot] = []
		async with self._lock:
			stale = [
				rid
				for rid, rs in self._runs.items()
				if (now - rs.updated_at).total_seconds() > _STALE_TTL_SECONDS
			]
			active_run_ids = [rid for rid in self._runs if rid not in stale]
			abandoned = [
				key
				for key, slot in self._agent_slots.items()
				if (now - slot.claimed_at).total_seconds() > _SLOT_TIMEOUT_SECONDS
			]
			for key in abandoned:
				logger.warning("evicting abandoned agent slot %s", key)
				slot = self._agent_slots.pop(key)
				slot.ready.set()
				abandoned_slots.append(slot)
		for slot in abandoned_slots:
			if slot.distributed_key is not None and slot.distributed_token is not None:
				await best_effort_teardown(
					partial(
						abandon_run_slot,
						slot.distributed_key,
						slot.distributed_token,
					)
				)
		for rid in active_run_ids:
			# the lease expires on its own if this cannot land, and the run's
			# own terminal path is what settles it - not the cleanup loop.
			await best_effort_teardown(partial(refresh_run_slot, rid))
		for rid in stale:
			logger.warning("evicting stale run %s", rid)
			await self.terminate_stale_run(rid)

	async def terminate_stale_run(self, run_id: TypeID) -> None:
		"""end a run that stopped publishing, as if it had failed.

		publishing is the heartbeat, so a run this quiet is wedged or gone.
		dropping it from the map silently would leave its producer running with
		no terminal event, no cancel, and its queued steering owing forever -
		so cancel the producer and let the normal failure path settle it.
		"""
		if self._on_stale_run is not None:
			await self._on_stale_run(run_id)
			return
		# no owner registered (tests, or an import order that never reached
		# run_failures): at minimum do not leave it in the map.
		if not await self.cancel_run(run_id, reason="run went silent"):
			await self.fail_run(run_id, reason="run went silent")

	def _detach_subscribers(self, run_id: TypeID) -> list[asyncio.Queue[bytes | None]]:
		"""take a run's subscribers out of the registry. caller holds the lock.

		detaching and delivering are separate so a terminal handler can claim
		the set inside its critical section (nothing can unsubscribe or GC it
		out from under the handler) and push the frames outside it.
		"""
		return list(self._subscribers.pop(run_id, {}))

	@staticmethod
	def _send(
		queues: list[asyncio.Queue[bytes | None]],
		frame: bytes | None,
		context_id: TypeID,
	) -> None:
		"""best-effort push to already-detached subscribers.

		never raises - QueueFull on a saturated subscriber must not crash a
		terminal handler. a subscriber whose queue is full has already received
		plenty of frames and will eventually drain; if it never does, the
		cleanup loop GC will handle it.

		``context_id`` is only for the log line, and is whichever id the caller
		was working from - a run when a run ends, a thread when access changes.
		"""
		for q in queues:
			try:
				q.put_nowait(frame)
			except asyncio.QueueFull:
				logger.warning(
					"subscriber queue full for %s, dropping %s",
					context_id,
					"sentinel" if frame is None else "frame",
				)

	# --- pub/sub ---

	async def _drain_mirror_queue(
		self,
		run_id: TypeID,
		queue: asyncio.Queue[bytes],
	) -> None:
		"""ship queued frames to Redis in batches until the queue runs dry.

		frames are batched because a run publishes far faster than one
		round-trip per frame would allow, and mirroring is not on the local
		subscriber's path - it exists for readers on other workers.
		"""
		try:
			while True:
				async with self._lock:
					try:
						first = queue.get_nowait()
					except asyncio.QueueEmpty:
						return
				batch = [first]
				await asyncio.sleep(0)
				while len(batch) < 128:
					try:
						batch.append(queue.get_nowait())
					except asyncio.QueueEmpty:
						break
				await mirror_frames(run_id, batch)
		finally:
			async with self._lock:
				if self._mirror_queues.get(run_id) is queue:
					self._mirror_queues.pop(run_id, None)
				self._mirror_tasks.pop(run_id, None)

	def _enqueue_mirror(self, run_id: TypeID, frame: bytes) -> None:
		"""queue one frame while the caller holds the state lock."""
		queue = self._mirror_queues.setdefault(run_id, asyncio.Queue())
		queue.put_nowait(frame)
		task = self._mirror_tasks.get(run_id)
		if task is None or task.done():
			self._mirror_tasks[run_id] = asyncio.create_task(
				self._drain_mirror_queue(run_id, queue),
				name=f"run-frame-mirror:{run_id}",
			)

	async def _flush_mirrors(self, run_id: TypeID) -> None:
		"""wait for a run's mirrored frames to land before it terminates.

		bounded and best-effort: a remote reader missing the last frames is
		worse than a slow terminal path, but not worse than one that hangs.
		"""
		async with self._lock:
			task = self._mirror_tasks.get(run_id)
		if task is None:
			return
		try:
			async with asyncio.timeout(5):
				await asyncio.shield(task)
		except Exception:
			logger.warning(
				"run frame mirror flush failed for %s",
				run_id,
				exc_info=True,
			)

	async def publish(self, run_id: TypeID, frame: bytes) -> None:
		"""record an SSE frame and push it to all subscribers.

		publishing is the run's heartbeat: the cleanup loop evicts on
		``updated_at``, and a run that is streaming is alive by definition even
		when nothing steers it for longer than the stale TTL.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			rs.sse_log.append(frame)
			if len(rs.sse_log) > RUN_LOG_MAX_FRAMES:
				del rs.sse_log[:-RUN_LOG_MAX_FRAMES]
				rs.sse_truncated = True
			rs.touch()
			queues = list(self._subscribers.get(run_id, {}))
			self._enqueue_mirror(run_id, frame)
			for queue in queues:
				try:
					queue.put_nowait(frame)
				except asyncio.QueueFull:
					logger.warning("disconnecting slow subscriber for run %s", run_id)
					self._subscribers.get(run_id, {}).pop(queue, None)
					while not queue.empty():
						queue.get_nowait()
					queue.put_nowait(sse_encode(event="truncated", data={}))
					queue.put_nowait(None)

	async def touch_run(self, run_id: TypeID) -> None:
		"""record liveness without publishing an SSE frame."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is not None:
				rs.touch()

	async def subscribe(
		self,
		run_id: TypeID,
		user_id: TypeID,
	) -> tuple[list[bytes], asyncio.Queue[bytes | None]] | None:
		"""subscribe to a run's SSE stream as one authorized user.

		returns (sse_log, live_queue) or None if the run doesn't exist.
		the caller should:
		1. replay all sse_log frames (catchup)
		2. read from live_queue until None sentinel (run ended)

		``user_id`` is who the caller was authorized as, which is what makes a
		mid-run revocation actionable: access is resolved once at subscribe
		time, and a stream that outlives the access it opened under has to be
		findable by user to be ended.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return None
			catchup_log = rs.sse_log
			truncated = rs.sse_truncated
			q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=4096)
			self._subscribers.setdefault(run_id, {})[q] = user_id
		catchup = list(catchup_log)
		if truncated:
			catchup.insert(0, sse_encode(event="truncated", data={}))
		return catchup, q

	async def unsubscribe(self, run_id: TypeID, q: asyncio.Queue[bytes | None]) -> None:
		"""remove a subscriber queue."""
		async with self._lock:
			subs = self._subscribers.get(run_id)
			if subs is not None:
				subs.pop(q, None)

	async def subscribed_user_ids(self, thread_id: TypeID) -> set[TypeID]:
		"""who is watching this thread's locally-owned runs right now."""
		async with self._lock:
			return {
				user_id
				for rs in self._runs.values()
				if rs.thread_id == thread_id
				for user_id in self._subscribers.get(rs.run_id, {}).values()
			}

	async def detach_thread_subscribers(
		self,
		thread_id: TypeID,
		user_ids: set[TypeID],
	) -> int:
		"""end these users' streams on a thread's runs, leaving the runs alone.

		losing access to a conversation ends the caller's view of it, not the
		answer being written into it for everyone else. the stream closes the
		way a completion does, so the client sees a finished stream rather than
		a connection that stops producing.
		"""
		if not user_ids:
			return 0
		async with self._lock:
			detached: list[asyncio.Queue[bytes | None]] = []
			for rs in self._runs.values():
				if rs.thread_id != thread_id:
					continue
				subs = self._subscribers.get(rs.run_id)
				if subs is None:
					continue
				for queue in [q for q, uid in subs.items() if uid in user_ids]:
					del subs[queue]
					detached.append(queue)
		for queue in detached:
			self._send([queue], None, thread_id)
		return len(detached)

	# --- mutations ---

	async def start_run(
		self,
		run_id: TypeID,
		agent_id: TypeID,
		user_id: TypeID,
		thread_id: TypeID | None = None,
		persist: bool = True,
	) -> RunSnapshot:
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
			persist=persist,
		)
		async with self._lock:
			self._runs[run_id] = rs
		return rs.snapshot()

	# conversation state

	async def bind(
		self,
		run_id: TypeID,
		container_root_id: TypeID | None,
		invocation_message_id: TypeID | None,
		read_through_message_id: TypeID | None = None,
		anchor_message_id: TypeID | None = None,
	) -> None:
		"""record which conversation this run answers, and from where.

		``read_through_message_id`` is the newest message already in the
		snapshot the run started from: catch-up measures its delta from there,
		so a mention arriving before the run reads anything hands over only
		what is actually new. without it the first catch-up re-injects the
		whole branch the agent was already given.

		``invocation_message_id`` additionally names the message the run was
		asked to answer, which seeds the first reply anchor. a regeneration has
		a boundary but nothing it replies to, so it passes only the former.

		``anchor_message_id`` is where the run renders. it defaults to the
		boundary, and a regeneration whose boundary is the thread head passes
		it explicitly - the run is not reading from there, but that is still
		where a failure belongs.

		binding is what makes the run reachable by catch-up, so the boundary
		must be settled here: a run announced with none accepts a "catch-up"
		measured from nothing, which is the whole branch.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			if rs.conversation_bound:
				return
			rs.container_root_id = container_root_id
			rs.conversation_bound = True
			boundary = invocation_message_id or read_through_message_id
			if boundary is not None:
				rs.queued_through_message_id = boundary
				rs.injected_through_message_id = boundary
			rs.anchor_message_id = anchor_message_id or boundary
			if invocation_message_id is not None:
				rs.reply_anchor_message_id = invocation_message_id
				rs.reply_anchor_pending = True
			rs.touch()

	async def set_container(
		self,
		run_id: TypeID,
		container_root_id: TypeID | None,
	) -> None:
		"""update only the conversation container after topology materializes."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			rs.container_root_id = container_root_id
			rs.touch()

	async def mark_catch_up_injected(
		self,
		run_id: TypeID,
		invocation_message_id: TypeID,
	) -> None:
		"""advance the conversation after one delivered catch-up."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			rs.injected_through_message_id = invocation_message_id
			rs.anchor_message_id = invocation_message_id
			rs.reply_anchor_message_id = invocation_message_id
			rs.reply_anchor_pending = True
			rs.touch()

	# agent startup slots

	def _active_run_for_invocation(
		self,
		thread_id: TypeID,
		agent_id: TypeID,
		container_root_id: TypeID | None,
	) -> RunStatus | None:
		"""caller must hold the store lock."""
		for rs in self._runs.values():
			if not rs.conversation_bound:
				continue
			if rs.thread_id != thread_id or rs.agent_id != agent_id:
				continue
			if same_container(rs.container_root_id, container_root_id):
				return rs
		return None

	@staticmethod
	def _slot_key(
		thread_id: TypeID,
		agent_id: TypeID,
		container_root_id: TypeID | None,
	) -> tuple[str, str, str]:
		"""the identity a startup slot is held under.

		one agent answering one conversation is one run, and the conversation
		is the thread plus its container - so a sub-thread and its canon
		thread hold separate slots for the same agent.
		"""
		return (str(thread_id), str(container_root_id or ""), str(agent_id))

	async def claim(
		self,
		thread_id: TypeID,
		agent_id: TypeID,
		container_root_id: TypeID | None,
	) -> AgentSlotClaim:
		"""decide, atomically, whether this caller starts the agent's run.

		one agent answering one conversation is one run, so exactly one of
		three things is true and the store settles which: a run is already
		answering (steer it), nobody is (this caller starts it), or another
		caller is mid-start (wait for that run, then steer it). checking the
		run map alone cannot settle it - a run being started is not in the map
		yet, which is how two invocations both conclude "nobody is answering".
		"""
		key = self._slot_key(thread_id, agent_id, container_root_id)
		async with self._agent_slot_claim_lock:
			expired: AgentSlot | None = None
			async with self._lock:
				active = self._active_run_for_invocation(
					thread_id, agent_id, container_root_id
				)
				if active is not None:
					return SteerExistingRun(run_id=active.run_id)
				pending = self._agent_slots.get(key)
				if pending is not None:
					age = (datetime.now(tz=UTC) - pending.claimed_at).total_seconds()
					if age <= _SLOT_TIMEOUT_SECONDS:
						return AwaitPendingRun(slot=pending)
					self._agent_slots.pop(key, None)
					pending.ready.set()
					expired = pending
			if (
				expired is not None
				and expired.distributed_key is not None
				and expired.distributed_token is not None
			):
				await best_effort_teardown(
					partial(
						abandon_run_slot,
						expired.distributed_key,
						expired.distributed_token,
					)
				)
			distributed = await claim_run_slot(
				thread_id,
				container_root_id,
				agent_id,
			)
			if isinstance(distributed, RunSlotActive):
				return SteerExistingRun(run_id=distributed.run_id)
			if isinstance(distributed, RunSlotPending):
				return AwaitPendingRun(
					slot=AgentSlot(
						ready=asyncio.Event(),
						distributed_key=distributed.key,
					)
				)
			slot = AgentSlot(
				ready=asyncio.Event(),
				distributed_key=distributed.key,
				distributed_token=distributed.token,
			)
			async with self._lock:
				self._agent_slots[key] = slot
			return StartNewRun(slot=slot)

	async def release(
		self,
		thread_id: TypeID,
		agent_id: TypeID,
		container_root_id: TypeID | None,
		slot: AgentSlot,
		run_id: TypeID | None,
	) -> None:
		"""publish the started run to whoever waited on this slot.

		``run_id`` is None when the start failed; waiters then re-claim rather
		than steer a run that does not exist.
		"""
		key = self._slot_key(thread_id, agent_id, container_root_id)
		async with self._lock:
			active = run_id is not None and run_id in self._runs
			slot.run_id = run_id if active else None
			if self._agent_slots.get(key) is slot:
				del self._agent_slots[key]
		slot.ready.set()
		if slot.distributed_key is None or slot.distributed_token is None:
			return
		if not active or run_id is None:
			await best_effort_teardown(
				partial(
					abandon_run_slot,
					slot.distributed_key,
					slot.distributed_token,
				)
			)
			return
		promoted = await promote_run_slot(
			slot.distributed_key,
			slot.distributed_token,
			run_id,
		)
		if not promoted:
			logger.error(
				"distributed run slot was replaced before registration",
				extra={"run_id": str(run_id)},
			)
			await self.cancel_run(run_id, reason="run slot ownership lost")

	async def wait(self, slot: AgentSlot) -> TypeID | None:
		"""wait for a claimed slot to publish its run id or fail to start."""
		if slot.distributed_key is not None and slot.distributed_token is None:
			return await wait_run_slot(slot.distributed_key)
		async with asyncio.timeout(_SLOT_TIMEOUT_SECONDS):
			await slot.ready.wait()
		return slot.run_id

	# catch-up reservations

	async def reserve_catch_up(
		self,
		run_id: TypeID,
		invocation_message_id: TypeID,
	) -> CatchUpReservation:
		"""claim the range a mention will catch this run up on.

		advancing the cursor under the store lock is what makes two racing
		mentions queue disjoint segments instead of the same messages twice.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return CatchUpRefused()
			if rs.queued_through_message_id == invocation_message_id:
				return CatchUpAlreadyAccepted()
			if len(rs.steering_inbox) >= _MAX_INBOX:
				return CatchUpRefused()
			previous = rs.queued_through_message_id
			rs.queued_through_message_id = invocation_message_id
			rs.touch()
			return CatchUpReserved(
				invocation_message_id=invocation_message_id,
				previous_invocation_id=previous,
			)

	async def release_catch_up(
		self,
		run_id: TypeID,
		reservation: CatchUpReserved,
	) -> None:
		"""undo a reservation whose batch never reached the run.

		only while this reservation still owns the cursor: a later mention may
		have reserved past it, and rewinding to our predecessor would re-ship
		the range that one already claimed.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			if rs.queued_through_message_id != reservation.invocation_message_id:
				return
			rs.queued_through_message_id = reservation.previous_invocation_id
			rs.touch()

	# conversation reply anchors

	async def reserve_reply_anchor(
		self, run_id: TypeID
	) -> ReplyAnchorReservation | None:
		"""claim the pending anchor for one accepted assistant output."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if (
				rs is None
				or not rs.reply_anchor_pending
				or rs.reply_anchor_message_id is None
				or rs.reply_anchor_claim_token is not None
			):
				return None
			token = str(new_typeid("reply_claim"))
			message_id = rs.reply_anchor_message_id
			rs.reply_anchor_pending = False
			rs.reply_anchor_claim_token = token
			rs.touch()
			return ReplyAnchorReservation(token=token, message_id=message_id)

	async def acknowledge_reply_anchor(
		self,
		run_id: TypeID,
		reservation: ReplyAnchorReservation,
	) -> None:
		"""consume an anchor after its assistant row commits."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None or rs.reply_anchor_claim_token != reservation.token:
				return
			rs.reply_anchor_claim_token = None
			rs.touch()

	async def release_reply_anchor(
		self,
		run_id: TypeID,
		reservation: ReplyAnchorReservation,
	) -> None:
		"""return an anchor whose assistant output did not commit."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None or rs.reply_anchor_claim_token != reservation.token:
				return
			rs.reply_anchor_claim_token = None
			if not rs.reply_anchor_pending:
				rs.reply_anchor_message_id = reservation.message_id
				rs.reply_anchor_pending = True
			rs.touch()

	async def read_through(self, run_id: TypeID) -> TypeID | None:
		"""the newest persisted message delivered into this run's context."""
		async with self._lock:
			rs = self._runs.get(run_id)
			return rs.injected_through_message_id if rs is not None else None

	# lifecycle tasks

	async def attach_task(self, run_id: TypeID, task: asyncio.Task[object]) -> None:
		"""attach the producer task to a run for cancel support."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is not None:
				rs.task = task

	async def attach_steering_task(
		self,
		run_id: TypeID,
		task: asyncio.Task[object],
	) -> None:
		"""attach the owning worker's steering command subscriber."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is not None:
				rs.steering_task = task

	async def cancel_run(self, run_id: TypeID, reason: str = "cancelled") -> bool:
		"""cancel a run's producer task. returns True if a task was cancelled.

		the task's cancellation handler is responsible for calling fail_run and
		broadcasting run.completed to clients. this method only triggers the
		cancellation - it does NOT remove the run from the store directly.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			task = rs.task if rs is not None else None
			if rs is not None:
				rs.cancellation_reason = reason
		if task is not None and not task.done():
			task.cancel()
			return True
		return False

	async def cancellation_reason(self, run_id: TypeID) -> str | None:
		"""return the reason supplied by the run's cancellation owner."""
		async with self._lock:
			rs = self._runs.get(run_id)
			return rs.cancellation_reason if rs is not None else None

	# steering inbox

	async def enqueue(self, run_id: TypeID, injection: Injection) -> bool:
		"""enqueue an injection for in-flight delivery.

		returns True if the run is alive and accepted it, False if the run is
		unknown, terminal, or the inbox is full. the agent loop drains the
		inbox between iterations via a ``SteeringFilter`` on the per-run agent.

		the append is performed under the lock so that a concurrent
		``claim_pending_steering`` cannot race past it and leave a stranded
		injection behind an already-cleared inbox.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return False
			if len(rs.steering_inbox) >= _MAX_INBOX:
				return False
			rs.steering_inbox.append(injection)
			rs.touch()
		return True

	async def mark_steering_injected(
		self, run_id: TypeID, message_ids: list[TypeID]
	) -> None:
		"""confirm in-flight claims as injected.

		called from the ``SteeringFilter.on_injected`` callback once the
		messages have been drained onto the thread, so terminal handlers no
		longer see them as owing a resolution. only ``claimed_steering`` is
		cleared: the inbox is the undelivered payload itself, so removing an
		unclaimed id from it would cancel a message rather than confirm one.
		no-op for unknown runs or empty input.
		"""
		if not message_ids:
			return
		injected = set(message_ids)
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return
			rs.claimed_steering = [
				mid for mid in rs.claimed_steering if mid not in injected
			]
			rs.touch()

	async def claim_inbox(self, run_id: TypeID) -> list[Injection]:
		"""atomically drain the inbox for in-line injection.

		draining under the store lock is what makes a concurrent
		``drop_pending_steering`` unambiguous: the drop either wins the lock
		and removes the injection before claim sees it, or loses and finds an
		empty inbox. that eliminates the race where the filter would inject a
		message into the thread while a drop flagged the same row dropped.

		retractable ids move into ``claimed_steering`` so a terminal handler
		landing in the window before ``mark_steering_injected`` still sees
		them as owing a resolution.

		callers (the SteeringFilter) treat the returned list as "definitively
		going into the thread" and MUST follow up with
		``mark_steering_injected`` once the on_injected callback completes.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return []
			drained = rs.steering_inbox
			if not drained:
				return []
			rs.steering_inbox = []
			rs.claimed_steering.extend(
				injection.message_id for injection in drained if injection.retractable
			)
			rs.touch()
			return drained

	async def drop_pending_steering(self, run_id: TypeID, message_id: TypeID) -> bool:
		"""remove a still-queued injection before the agent drains it.

		returns True if it was found and removed; False if unknown (already
		injected, already dropped, or never queued here). matched by id rather
		than position, so the inbox needs no parallel bookkeeping to stay
		consistent with.

		only retractable injections can be dropped: this is reachable from
		``DELETE /runs/{id}/steer/{message_id}``, and a catch-up is the
		server's own decision to hand a run conversation it already owes an
		answer to, not a user-owned message to take back.
		"""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return False
			remaining = [
				injection
				for injection in rs.steering_inbox
				if not (injection.retractable and injection.message_id == message_id)
			]
			if len(remaining) == len(rs.steering_inbox):
				return False
			rs.steering_inbox = remaining
			rs.touch()
		return True

	async def complete_run(self, run_id: TypeID) -> RunSnapshot | None:
		"""mark a run as completed and close subscribers.

		only the ``None`` sentinel is delivered; subscribe_run_stream synthesizes
		the terminal SSE ``done`` event so we don't double-signal.
		"""
		async with self._lock:
			rs = self._runs.pop(run_id, None)
			if rs is not None:
				rs.state = RunState.COMPLETED
				rs.touch()
			# detach under the lock to avoid racing with subscribe /
			# unsubscribe / cleanup_loop; deliver outside it.
			subscribers = self._detach_subscribers(run_id)
		if rs is None:
			return None
		if rs.steering_task is not None:
			rs.steering_task.cancel()
		self._send(subscribers, None, run_id)
		# tell remote subscribers (other workers) that the stream is done, then
		# mark the catchup log for short-grace expiry. cleanup_run_log uses
		# EXPIRE rather than DELETE so a late cross-worker subscriber landing
		# within the grace window still sees the catchup; subsequent
		# subscribers find the key expired and get a lone terminal frame.
		await self._flush_mirrors(run_id)
		await mark_run_end(run_id)
		await best_effort_teardown(partial(cleanup_run_log, run_id))
		await best_effort_teardown(partial(release_run_slot, run_id))
		return rs.snapshot()

	async def fail_run(
		self,
		run_id: TypeID,
		reason: str | None = None,
	) -> RunSnapshot | None:
		"""mark a run as errored, push the error frame, and close subscribers.

		the public error frame carries only ``run_id`` and a ``RunFailureReason``
		so late/resume subscribers do not receive provider, model, status, code,
		or internal reason details. that closed set is the same value the
		durable ``run.error`` fans out, so the live and durable channels never
		disagree about why one run stopped. the terminal ``done`` event is
		synthesized by subscribe_run_stream from the ``None`` sentinel.

		idempotent: if the run is already gone (e.g. concurrent fail/complete)
		this returns ``None`` and is otherwise a no-op.
		"""
		async with self._lock:
			rs = self._runs.pop(run_id, None)
			if rs is None:
				return None
			# the run is out of the map, so this only marks the snapshot the
			# caller gets back - but `complete_run` sets COMPLETED on its own
			# snapshot, and a failed run reading RUNNING is a lie to anyone
			# holding it.
			rs.state = RunState.ERROR
			rs.touch()
			if rs.steering_task is not None:
				rs.steering_task.cancel()
			# detach under the lock so a concurrent unsubscribe or
			# _close_subscribers (e.g. from cleanup_loop) can't yank the set out
			# from under us; the post-lock pass is purely best-effort delivery.
			subscribers = self._detach_subscribers(run_id)
		err_payload = {"run_id": str(run_id), "reason": classify_failure(reason).value}
		err_frame = sse_encode(event="error", data=err_payload)
		# mirror the error frame to redis so cross-worker late subscribers
		# see the sanitized failure via the catchup LRANGE; without this they
		# only see the end sentinel and lose the terminal error state.
		self._send(subscribers, err_frame, run_id)
		self._send(subscribers, None, run_id)
		await self._flush_mirrors(run_id)
		await mirror_frame(run_id, err_frame)
		# tell remote subscribers the stream ended; cleanup_run_log uses
		# a short EXPIRE so late cross-worker subscribers within the grace
		# window still get the catchup + the mirrored error frame.
		await mark_run_end(run_id)
		await best_effort_teardown(partial(cleanup_run_log, run_id))
		await best_effort_teardown(partial(release_run_slot, run_id))
		return rs.snapshot()

	# --- queries ---

	async def get_run(self, run_id: TypeID) -> RunSnapshot | None:
		"""get a single run by ID."""
		async with self._lock:
			rs = self._runs.get(run_id)
			return rs.snapshot() if rs is not None else None

	async def has_in_flight_steering(self, run_id: TypeID) -> bool:
		"""return whether a running API run still has steering to settle."""
		async with self._lock:
			rs = self._runs.get(run_id)
			if rs is None:
				return False
			return bool(rs.steering_inbox or rs.claimed_steering)

	async def get_all_active_runs(self) -> list[RunSnapshot]:
		"""get all currently active runs across all threads."""
		async with self._lock:
			return [rs.snapshot() for rs in self._runs.values()]

	async def local_run_ids(self, thread_id: TypeID) -> list[TypeID]:
		"""IDs of active runs owned by this process for one thread."""
		async with self._lock:
			return [
				rs.run_id for rs in self._runs.values() if rs.thread_id == thread_id
			]

	async def get_runs_for_user(self, user_id: TypeID) -> list[RunSnapshot]:
		"""get all active runs owned by a specific user."""
		async with self._lock:
			return [
				rs.snapshot() for rs in self._runs.values() if rs.user_id == user_id
			]


run_store = RunStore()
"""the process's one run store, behind every alias below."""
run_registry = run_store
"""the store as run lifecycle: start, cancel, complete, fail."""
run_streams = run_store
"""the store as SSE pub/sub: publish, subscribe, catchup."""
run_conversations = run_store
"""the store as conversation state: binding, boundaries, reply anchors."""
run_inbox = run_store
"""the store as steering inbox: enqueue, claim, drop, catch-up reservations."""
agent_slots = run_store
"""the store as startup slots: one agent answering one conversation.

one object wearing six names: the state is genuinely shared - a slot resolves
into a run, whose inbox feeds its stream - and splitting it would mean four
stores taking each other's locks. the aliases keep each call site honest about
which concern it is touching.
"""


async def get_active_runs_signal(user_id: TypeID) -> ActiveRunsSignal:
	"""build a single WS signal listing active agent runs for the user.

	returns a ready-to-send dict ``{type: 'runs.active', data: [...]}``.
	an empty ``data`` list is meaningful: it tells the client to clear any
	stale active-run pointers from a previous connection. this is NOT catchup
	data - it's a lightweight pointer list so the client knows which runs to
	resume via the SSE endpoint.
	"""
	# collect thread IDs from all currently active runs
	all_runs = await run_registry.get_all_active_runs()
	if not all_runs:
		return {"type": "runs.active", "data": []}

	unique_thread_ids = {rs.thread_id for rs in all_runs if rs.thread_id is not None}

	# resolve which of those threads the user can access
	accessible_threads: set[TypeID] = set()
	async with async_session_local() as db_session:
		principal = await load_principal_for_user(user_id, db_session)
		accessible_threads.update(
			await db_session.scalars(
				select(Thread.id).where(
					Thread.id.in_(unique_thread_ids),
					resource_access_predicate(
						principal,
						ResourceType.THREAD,
						required_level=AccessLevel.READER,
					),
				)
			)
		)

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
