"""cross-worker run stream and routing bus."""

import asyncio
import contextlib
import json
import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Final, Literal, cast

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from api.redis import SseFrameBus, make_run_channel
from api.redis.client import redis_client
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, is_typeid


logger = logging.getLogger(__name__)

_BUS_FAILURES = (RedisError, RuntimeError, OSError)
"""what an unreachable cache backend raises on the way through this module."""


class RunBusUnavailableError(HTTPException):
	"""raised when the bus a run needs to coordinate on cannot be reached.

	the cache backend is a hard dependency of runs, not a cache in front of
	one: the slot is what keeps one agent to one conversation across workers,
	and the route is what lets any worker reach a run at all. carrying on
	locally would silently trade those guarantees for a run that looks fine
	from the worker that started it, so a caller on the startup path gets a
	503 instead.
	"""

	def __init__(self, operation: str) -> None:
		"""name the bus operation that could not be completed."""
		super().__init__(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="agent runs are temporarily unavailable; please try again shortly",
		)
		self.operation = operation


class RunSlotContendedError(HTTPException):
	"""raised when a startup slot kept changing hands while we claimed it.

	distinct from an unreachable bus: the backend answered every time, and
	another worker simply won each round. that is a live conflict over one
	agent's conversation rather than an outage, so it says so - and retrying
	is a decision for whoever is contending, not a blanket "try later".
	"""

	def __init__(self, key: str) -> None:
		"""name the slot that could not be settled."""
		super().__init__(
			status_code=status.HTTP_409_CONFLICT,
			detail="this agent is already being started in this conversation",
		)
		self.key = key


@contextlib.asynccontextmanager
async def _bus_call(operation: str) -> AsyncIterator[None]:
	"""translate any cache-backend failure into the one run-bus error."""
	try:
		yield
	except _BUS_FAILURES as exc:
		raise RunBusUnavailableError(operation) from exc


async def best_effort_teardown(
	operation: Callable[[], Coroutine[object, object, None]],
) -> None:
	"""run one bus teardown call that has nothing left to fail into.

	the startup path fails a run outright when the bus is unreachable, but a
	run that already ended cannot be un-ended: refusing to release its slot
	would only leave the terminal path broken as well. the keys these calls
	touch all carry a TTL, so an unreachable bus expires them on its own.
	"""
	try:
		await operation()
	except RunBusUnavailableError as exc:
		logger.warning("run bus teardown skipped: %s unreachable", exc.operation)


_LOG_TTL_SECONDS: Final[int] = 10 * 60
"""catchup window for an active run; matches the in-process stale TTL."""
RUN_LOG_MAX_FRAMES: Final[int] = 4096
"""maximum retained frames for one remote run catchup."""
_LOG_CLEANUP_GRACE_SECONDS: Final[int] = 5
"""seconds a completed run remains available for late remote catchup."""
_ROUTE_PREFIX: Final[str] = "nokodo-ai:run:"
"""key namespace for everything stored per run."""
_SLOT_PREFIX: Final[str] = "nokodo-ai:run-slot:"
"""key namespace for the one-agent-per-conversation mutual exclusion token."""
PENDING_RUN_SLOT_TTL_SECONDS: Final[int] = 30
"""how long a slot may stay unresolved before another caller may take it.

bounds the window a crashed launcher can block an agent's conversation for.
"""
ACTIVE_RUN_SLOT_TTL_SECONDS: Final[int] = 60
"""lease an active run renews to keep holding its slot.

short on purpose: this is a mutual-exclusion token, so a dead worker must
release it quickly. the route it accompanies keeps its own longer window.
"""

_bus: Final[SseFrameBus] = SseFrameBus(
	key_prefix=_ROUTE_PREFIX,
	end_marker=b"nokodo-ai:run-end",
	channel_factory=make_run_channel,
	log_ttl_seconds=_LOG_TTL_SECONDS,
	max_frames=RUN_LOG_MAX_FRAMES,
	cleanup_grace_seconds=_LOG_CLEANUP_GRACE_SECONDS,
	truncated_marker=sse_encode(event="truncated", data={}),
)
"""cross-worker mirror of every run's SSE frames, and their replay log."""


@dataclass(frozen=True, slots=True)
class RunRoute:
	"""cross-worker coordinates for one run's owner."""

	thread_id: TypeID | None
	"""conversation the run answers; None for an ephemeral run."""
	container_root_id: TypeID | None
	"""sub-thread the run answers in; None for the canon conversation."""
	agent_id: TypeID
	"""agent doing the answering."""
	user_id: TypeID
	"""user who started the run, which is who governs an ephemeral one."""
	persist: bool
	"""whether the run writes its output to the conversation."""


@dataclass(frozen=True, slots=True)
class RunSlotOwner:
	"""a distributed startup slot claimed by this worker."""

	key: str
	"""slot this worker holds."""
	token: str
	"""proves the hold is still ours when we promote or release it."""


@dataclass(frozen=True, slots=True)
class RunSlotPending:
	"""a distributed startup slot owned by another worker."""

	key: str
	"""slot to wait on for the run that worker is starting."""


@dataclass(frozen=True, slots=True)
class RunSlotActive:
	"""an active run already owns the distributed slot."""

	run_id: TypeID
	"""the run answering here, which a caller steers instead of starting one."""


type RunSlotClaim = RunSlotOwner | RunSlotPending | RunSlotActive
"""what a caller found when it tried to claim an agent's conversation.

exactly one of three things is true, so callers match on the case rather than
rebuilding it from which fields happen to be set.
"""
type StoredRunSlot = Literal["pending"] | RunSlotActive
"""what a slot key holds: a start in progress, or the run that won it."""


def _route_key(run_id: TypeID) -> str:
	"""key holding one run's cross-worker coordinates."""
	return f"{_ROUTE_PREFIX}{run_id}:route"


def _slot_key(
	thread_id: TypeID,
	container_root_id: TypeID | None,
	agent_id: TypeID,
) -> str:
	"""key naming one agent's claim on one conversation.

	the container is part of the key because an agent answering a sub-thread
	is not answering the canon conversation.
	"""
	return f"{_SLOT_PREFIX}{thread_id}:{container_root_id or 'canon'}:{agent_id}"


def _run_slot_key(run_id: TypeID) -> str:
	"""key pointing from a run back to the slot it holds."""
	return f"{_ROUTE_PREFIX}{run_id}:slot"


def _slot_value(raw: bytes | bytearray | None) -> StoredRunSlot | None:
	"""read a stored slot, or None when it is missing or unrecognized."""
	if raw is None:
		return None
	value = bytes(raw).decode("utf-8", errors="ignore")
	if value.startswith("pending:"):
		return "pending"
	if value.startswith("run:"):
		run_id = value.removeprefix("run:")
		if is_typeid(run_id, prefix="run"):
			return RunSlotActive(run_id=TypeID(run_id))
	return None


async def claim_run_slot(
	thread_id: TypeID,
	container_root_id: TypeID | None,
	agent_id: TypeID,
) -> RunSlotClaim:
	"""atomically claim or inspect one cross-worker agent startup slot."""
	key = _slot_key(thread_id, container_root_id, agent_id)
	async with _bus_call("claim_run_slot"):
		conn = redis_client.get()
		for _attempt in range(2):
			token = secrets.token_urlsafe(24)
			owned = await conn.set(
				key,
				f"pending:{token}",
				ex=PENDING_RUN_SLOT_TTL_SECONDS,
				nx=True,
			)
			if owned:
				return RunSlotOwner(key=key, token=token)
			raw = await conn.get(key)
			value = _slot_value(raw if isinstance(raw, (bytes, bytearray)) else None)
			if isinstance(value, RunSlotActive):
				return value
			if value == "pending":
				return RunSlotPending(key=key)
	# two full rounds of losing the SET and then finding the key gone means
	# something is churning this slot; a third would be guessing. the bus
	# answered every time, so this is contention, not an outage.
	logger.warning("run slot changed under every claim attempt: %s", key)
	raise RunSlotContendedError(key)


async def wait_run_slot(key: str) -> TypeID | None:
	"""wait for another worker's pending slot to publish its run id."""
	async with _bus_call("wait_run_slot"):
		conn = redis_client.get()
		loop = asyncio.get_running_loop()
		deadline = loop.time() + PENDING_RUN_SLOT_TTL_SECONDS
		delay = 0.05
		while loop.time() < deadline:
			raw = await conn.get(key)
			value = _slot_value(raw if isinstance(raw, (bytes, bytearray)) else None)
			if isinstance(value, RunSlotActive):
				return value.run_id
			if value is None:
				return None
			await asyncio.sleep(delay)
			delay = min(delay * 2, 0.5)
	raise TimeoutError


async def promote_run_slot(key: str, token: str, run_id: TypeID) -> bool:
	"""publish a started run only if this worker still owns its pending slot."""
	script = """
	if redis.call('GET', KEYS[1]) == ARGV[1] then
		redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
		redis.call('SET', KEYS[2], KEYS[1], 'EX', ARGV[3])
		return 1
	end
	if redis.call('EXISTS', KEYS[1]) == 0 then
		redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
		redis.call('SET', KEYS[2], KEYS[1], 'EX', ARGV[3])
		return 1
	end
	return 0
	"""
	async with _bus_call("promote_run_slot"):
		result = await cast(
			"Awaitable[object]",
			redis_client.get().eval(
				script,
				2,
				key,
				_run_slot_key(run_id),
				f"pending:{token}",
				f"run:{run_id}",
				ACTIVE_RUN_SLOT_TTL_SECONDS,
			),
		)
	return bool(result)


async def abandon_run_slot(key: str, token: str) -> None:
	"""drop a pending slot only if this worker still owns it."""
	script = """
	if redis.call('GET', KEYS[1]) == ARGV[1] then
		return redis.call('DEL', KEYS[1])
	end
	return 0
	"""
	async with _bus_call("abandon_run_slot"):
		await cast(
			"Awaitable[object]",
			redis_client.get().eval(script, 1, key, f"pending:{token}"),
		)


async def release_run_slot(run_id: TypeID) -> None:
	"""drop an active slot only if it still names this run."""
	script = """
	local slot = redis.call('GET', KEYS[1])
	if slot and redis.call('GET', slot) == ARGV[1] then
		redis.call('DEL', slot)
	end
	return redis.call('DEL', KEYS[1])
	"""
	async with _bus_call("release_run_slot"):
		await cast(
			"Awaitable[object]",
			redis_client.get().eval(
				script,
				1,
				_run_slot_key(run_id),
				f"run:{run_id}",
			),
		)


async def refresh_run_slot(run_id: TypeID) -> None:
	"""refresh active route and slot leases while a run publishes output.

	the slot keys carry the short mutual-exclusion lease; the route carries the
	catchup window, so each is refreshed with its own TTL.
	"""
	script = """
	local slot = redis.call('GET', KEYS[1])
	if slot and redis.call('GET', slot) == ARGV[1] then
		redis.call('EXPIRE', slot, ARGV[2])
		redis.call('EXPIRE', KEYS[1], ARGV[2])
	end
	redis.call('EXPIRE', KEYS[2], ARGV[3])
	return 1
	"""
	async with _bus_call("refresh_run_slot"):
		await cast(
			"Awaitable[object]",
			redis_client.get().eval(
				script,
				2,
				_run_slot_key(run_id),
				_route_key(run_id),
				f"run:{run_id}",
				ACTIVE_RUN_SLOT_TTL_SECONDS,
				_LOG_TTL_SECONDS,
			),
		)


async def register_run_route(run_id: TypeID, route: RunRoute) -> None:
	"""publish the coordinates needed to authorize and route remote requests."""
	payload = json.dumps(
		{
			"thread_id": str(route.thread_id) if route.thread_id is not None else None,
			"container_root_id": (
				str(route.container_root_id)
				if route.container_root_id is not None
				else None
			),
			"agent_id": str(route.agent_id),
			"user_id": str(route.user_id),
			"persist": route.persist,
		},
		separators=(",", ":"),
	)
	async with _bus_call("register_run_route"):
		await redis_client.get().set(
			_route_key(run_id),
			payload,
			ex=_LOG_TTL_SECONDS,
		)


async def read_run_route(run_id: TypeID) -> RunRoute | None:
	"""read one active or recently-finished run's routing coordinates.

	raises rather than reporting "no such run": a caller that cannot read the
	route has not established the run is gone, and answering 404 to a request
	about a live run is worse than answering 503.
	"""
	async with _bus_call("read_run_route"):
		raw = await redis_client.get().get(_route_key(run_id))
	if not isinstance(raw, (bytes, bytearray)):
		return None
	try:
		payload = json.loads(raw)
	except json.JSONDecodeError, UnicodeDecodeError:
		return None
	if not isinstance(payload, dict):
		return None
	thread_id = payload.get("thread_id")
	container_root_id = payload.get("container_root_id")
	agent_id = payload.get("agent_id")
	user_id = payload.get("user_id")
	persist = payload.get("persist")
	if (
		(thread_id is not None and not isinstance(thread_id, str))
		or (container_root_id is not None and not isinstance(container_root_id, str))
		or not isinstance(agent_id, str)
		or not isinstance(user_id, str)
		or not isinstance(persist, bool)
	):
		return None
	return RunRoute(
		thread_id=TypeID(thread_id) if thread_id is not None else None,
		container_root_id=(
			TypeID(container_root_id) if container_root_id is not None else None
		),
		agent_id=TypeID(agent_id),
		user_id=TypeID(user_id),
		persist=persist,
	)


async def mirror_frame(run_id: TypeID, frame: bytes) -> None:
	"""mirror a single SSE frame to Redis for cross-worker subscribers."""
	await _bus.mirror_frame(str(run_id), frame)


async def mirror_frames(run_id: TypeID, frames: list[bytes]) -> None:
	"""mirror an ordered frame batch for one run."""
	await _bus.mirror_frames(str(run_id), frames)


async def mark_run_end(run_id: TypeID) -> None:
	"""publish the end-of-stream sentinel for one run."""
	await _bus.mark_end(str(run_id))


def subscribe_remote_run(run_id: TypeID) -> AsyncIterator[bytes]:
	"""subscribe to a run owned by another worker."""
	return _bus.subscribe(str(run_id))


async def cleanup_run_log(run_id: TypeID) -> None:
	"""shrink Redis stream and route TTLs after a run terminates."""
	await _bus.cleanup_log(str(run_id))
	async with _bus_call("cleanup_run_log"):
		await redis_client.get().expire(_route_key(run_id), _LOG_CLEANUP_GRACE_SECONDS)
