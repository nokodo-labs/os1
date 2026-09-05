"""shared run infrastructure contracts."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from api.schemas.message import MessageSplice
from nokodo_ai.adapters.base.chat import GENERATION_FAILURE_REASONS
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.utils.typeid import TypeID


class SteeringInjection(Protocol):
	"""one claimed unit of externally supplied conversation."""

	@property
	def messages(self) -> list[SDKMessage]:
		"""what this injection puts into the agent's thread, in order."""
		...


@dataclass(frozen=True, slots=True)
class PersistedRunInput:
	"""the input message a run starts from, captured where it was written.

	the launcher writes the row and the producer answers it, in two sessions.
	everything the producer needs is read off the hot row at write time, so the
	producer neither re-queries it nor re-authorizes a principal that just
	wrote it.
	"""

	message_id: TypeID
	"""the persisted row this run answers."""
	splice: MessageSplice
	"""where the write placed it."""
	sdk_message: SDKUserMessage
	"""the same row as the model reads it."""
	created_frame: dict[str, object]
	"""the ``message_created`` payload announcing it on the run's stream."""
	container_root_id: TypeID | None
	"""sub-thread it landed in; None for the canon conversation."""


def same_container(left: TypeID | None, right: TypeID | None) -> bool:
	"""whether two container roots name the same conversation.

	None is the canon conversation rather than an absent one, so it compares
	equal to itself.
	"""
	return (left or None) == (right or None)


type KeyedLockRegistry = dict[TypeID, tuple[asyncio.Lock, int]]
"""per-key locks with the number of holders and waiters currently on each."""


@contextlib.asynccontextmanager
async def keyed_lock(
	registry: KeyedLockRegistry,
	guard: asyncio.Lock,
	key: TypeID,
) -> AsyncIterator[None]:
	"""hold one lock per key, refcounted so idle keys leave nothing behind.

	the registry would otherwise grow one entry per run or thread the process
	has ever seen.
	"""
	async with guard:
		entry = registry.get(key)
		if entry is None:
			lock = asyncio.Lock()
			registry[key] = (lock, 1)
		else:
			lock, users = entry
			registry[key] = (lock, users + 1)
	try:
		async with lock:
			yield
	finally:
		async with guard:
			entry = registry.get(key)
			if entry is None:
				return
			current_lock, users = entry
			if current_lock is not lock:
				return
			if users == 1:
				registry.pop(key, None)
			else:
				registry[key] = (lock, users - 1)


class RunFailureReason(StrEnum):
	"""why a run stopped without answering.

	a closed set: this record persists and fans out to every participant, so it
	must never carry provider, model, status, or internal exception detail.
	"""

	CANCELLED = "cancelled"
	"""someone stopped the run on purpose."""
	ACCESS_CHANGED = "access_changed"
	"""the thread's writer model moved out from under a live run."""
	INTERNAL_ERROR = "internal_error"
	"""anything we will not describe to a client in more detail."""
	UNAVAILABLE = "unavailable"
	"""a required backend was unreachable; the run may be retried."""
	PROVIDER_ERROR = "provider_error"
	"""the chat model refused or failed the generation."""
	NEVER_STARTED = "never_started"
	"""no run ever existed for the agent this message addressed."""
	NOT_DELIVERED = "not_delivered"
	"""the agent is answering here, but this message never reached its run."""


BUS_UNAVAILABLE_REASON = "bus unavailable"
"""internal reason string a run carries when the bus could not be reached.

the one value `classify_failure` maps onto ``UNAVAILABLE``, so "retry later"
is distinguishable from "we hit a bug" without naming which backend it was.
"""


def classify_failure(reason: str | None) -> RunFailureReason:
	"""map an internal failure reason onto the public enum.

	anything unrecognized is an internal error rather than a passthrough, so a
	new internal string can never leak into the durable record.
	"""
	if reason == "cancelled":
		return RunFailureReason.CANCELLED
	if reason == "access changed":
		return RunFailureReason.ACCESS_CHANGED
	if reason == BUS_UNAVAILABLE_REASON:
		return RunFailureReason.UNAVAILABLE
	if reason in GENERATION_FAILURE_REASONS:
		return RunFailureReason.PROVIDER_ERROR
	return RunFailureReason.INTERNAL_ERROR
