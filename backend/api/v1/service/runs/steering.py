"""run-steering persistence, delivery, and broadcasts."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException, status
from pydantic import ConfigDict, Field, SkipValidation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.database.advisory_locks import acquire_resource_write_lock
from api.local_tasks import create_background_task
from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message as MessageORM
from api.models.message import MessageType
from api.permissions import MentionableSubjectType, ResourceType
from api.schemas.message import MessageCreate, MessageSplice
from api.v1.service.authentication import Principal
from api.v1.service.chat.message_metadata import (
	CLIENT_STEERING_ID_KEY,
	CREATED_AT_KEY,
	STEERING_DROPPED_AT_KEY,
	STEERING_ENQUEUED_AT_KEY,
	STEERING_INJECTED_AT_KEY,
	get_message_id,
)
from api.v1.service.chat.messages import (
	build_steering_sdk_message,
	orm_message_to_sdk_message,
	run_input_text,
	validate_message_input,
)
from api.v1.service.events import broadcast_to_resource, fanout_event
from api.v1.service.runs.contracts import (
	KeyedLockRegistry,
	SteeringInjection,
	keyed_lock,
	same_container,
)
from api.v1.service.runs.resolution import (
	ResolvedRun,
	authorize_run,
	find_run,
	require_steerable_thread,
	resolve_authorized_run,
)
from api.v1.service.runs.status import (
	CatchUpAlreadyAccepted,
	CatchUpReserved,
	run_inbox,
	run_registry,
)
from api.v1.service.runs.steering_bus import (
	DropSteeringCommand,
	EnqueueSteeringCommand,
	InvocationSteeringCommand,
	publish_steering_command,
)
from api.v1.service.threads import (
	MessageDraft,
	Thread,
	apply_existing_message_splice,
	branch_root_id,
	create_message,
	is_multi_writer_thread,
	message_mentions_agent,
	messages_between,
)
from api.v1.service.threads.common import message_event_data, message_load_options
from nokodo_ai import Agent as SDKAgent
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.filters import Filter
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_catch_up_locks: KeyedLockRegistry = {}
"""per-run locks serializing catch-up reservations for one run."""
_catch_up_locks_guard = asyncio.Lock()
"""guards the catch-up lock registry itself."""


SteeringState = Literal["queued", "dropped"]
"""outcome a steering request reports to the caller that made it."""
PersistedSteeringState = Literal["queued", "injected", "dropped"]
"""``metadata.steering_state`` a steering row can hold.

``injected`` is absent from ``SteeringState`` because a request never returns
it: the agent reads the message later, long after the response was sent.
"""
SteeringParentProvider = Callable[[], TypeID | None]
"""reads the run's current output parent at injection time."""
SteeringRequireProcessed = Callable[[TypeID | None], Awaitable[None]]
"""waits for one output message to finish its run coordination."""
SteeringAdvanceParent = Callable[[TypeID], Awaitable[None]]
"""moves the run's output parent onto a just-injected message."""
SteeringReady = Callable[[], bool]
"""whether the run can take an injection at this iteration boundary."""
SteeringClaimCallback = Callable[[], Awaitable[list[SteeringInjection]]]
"""drains whatever the run's inbox is holding."""
SteeringInjectedCallback = Callable[
	[list[SteeringInjection]], Awaitable[list[SteeringInjection]]
]
"""settles a drained batch and returns what actually entered the thread."""


class SteeringFilter[AppContextT = None](Filter[AppContextT]):
	"""drain externally enqueued messages between agent iterations."""

	name: str = "steering"
	"""identifies this filter in the agent's filter chain."""
	description: str = (
		"drains externally-enqueued user messages into the thread between"
		" agent iterations"
	)
	"""what this filter does, for anyone inspecting the chain."""
	model_config = ConfigDict(arbitrary_types_allowed=True)
	"""the callbacks below are plain callables, which pydantic cannot validate."""
	claim: SkipValidation[SteeringClaimCallback] = Field(...)
	"""takes everything the run's inbox is holding."""
	on_injected: SkipValidation[SteeringInjectedCallback | None] = Field(default=None)
	"""settles a drained batch and reports what the thread accepted."""
	ready: SkipValidation[SteeringReady | None] = Field(default=None)
	"""whether the run can take an injection right now."""

	async def process(
		self,
		state: AgentIterationState[AppContextT],
		agent_context: AgentContext,
		app_context: AppContextT | None,
	) -> AgentIterationState[AppContextT]:
		"""drain the run's inbox into the thread between two iterations.

		the settlement is shielded so a cancel cannot tear a half-written
		injection, but a cancel that arrives still ends the run once the write
		lands - it is re-raised rather than absorbed.
		"""
		_ = (agent_context, app_context)
		if self.ready is not None and not self.ready():
			return state
		drained = await self.claim()
		if not drained:
			return state

		async def _settle_and_append() -> AgentIterationState[AppContextT]:
			"""persist the batch, then append what it accepted to the thread."""
			accepted = (
				await self.on_injected(drained)
				if self.on_injected is not None
				else drained
			)
			for injection in accepted:
				for message in injection.messages:
					state.thread.add(message)
			return state

		settlement = create_background_task(
			_settle_and_append(),
			name="settle_steering_injection",
		)
		cancelled = False
		deadline = asyncio.get_running_loop().time() + 30
		while True:
			remaining = deadline - asyncio.get_running_loop().time()
			if remaining <= 0:
				settlement.cancel()
				raise TimeoutError("steering settlement timed out")
			try:
				result = await asyncio.wait_for(
					asyncio.shield(settlement),
					remaining,
				)
				break
			except asyncio.CancelledError:
				cancelled = True
			except TimeoutError:
				settlement.cancel()
				raise
		if cancelled:
			raise asyncio.CancelledError
		return result


@dataclass(frozen=True, slots=True)
class SteeringResult:
	"""outcome of an ``enqueue_run_steering`` call."""

	message_id: TypeID
	"""the row the caller can render and later retract."""
	state: SteeringState
	"""whether the run took it, or ended before it could."""


@dataclass(frozen=True, slots=True)
class QueuedSteering:
	"""a message a user sent straight to a run, awaiting its real position.

	persisted as a ghost row before the agent has read it, so a run that dies
	owing one must retract it - hence ``retractable``.
	"""

	message_id: TypeID
	"""the persisted ghost row this injection will finalize."""
	message: SDKUserMessage
	"""what the agent reads when the loop drains this."""
	retractable: bool = True
	"""a run that dies owing this must flip its row to dropped."""

	@property
	def messages(self) -> list[SDKMessage]:
		"""the one message this injection carries."""
		return [self.message]


@dataclass(frozen=True, slots=True)
class InvocationCatchUp:
	"""the conversation a run missed, ending at the message that invoked it.

	these rows already sit where they belong in the shared branch, so the only
	thing this changes is what the agent has read. nothing was written on its
	behalf, so an undelivered one has nothing to retract - only a cursor to
	release, which ``release_catch_up`` owns.
	"""

	message_id: TypeID
	"""the invocation this batch catches the run up to."""
	messages: list[SDKMessage]
	"""the conversation the run missed, in chain order."""
	retractable: bool = False
	"""nothing was written for this, so an undelivered one owes no retraction."""


def remote_steering_injection(
	command: EnqueueSteeringCommand,
) -> QueuedSteering | InvocationCatchUp:
	"""restore one Redis command to the owning worker's inbox type."""
	if command.retractable:
		message = command.messages[0]
		if not isinstance(message, SDKUserMessage):
			raise ValueError("text steering command must carry one user message")
		return QueuedSteering(message_id=command.message_id, message=message)
	return InvocationCatchUp(
		message_id=command.message_id,
		messages=command.messages,
	)


async def settle_remote_steering_drop(
	run_id: TypeID,
	command: DropSteeringCommand,
) -> None:
	"""persist and announce one drop accepted by the owning worker."""
	await _settle_drop(
		message_id=command.message_id,
		thread_id=command.thread_id,
		agent_id=command.agent_id,
		run_id=run_id,
	)


async def enqueue_run_steering(
	run_id: TypeID,
	run_input: MessageCreate,
	parent_id: TypeID | None,
	client_steering_id: str | None,
	principal: Principal,
	db: AsyncSession,
) -> SteeringResult:
	"""persist a new message and enqueue it for a running agent.

	on success the persisted message is returned with state=``queued`` and a
	``run.steering.queued`` event is broadcast. the owning worker (which
	may or may not be this one) handles the late-drop case via the
	in-flight terminal handlers.

	raises ``HTTPException`` for the usual auth / not-found / 422 cases so
	the router can simply ``return await enqueue_run_steering(...)``.
	"""
	resolved = await resolve_authorized_run(
		run_id,
		principal,
		db,
		required_level=AccessLevel.EDITOR,
	)
	thread_id = require_steerable_thread(resolved)
	agent_id = resolved.agent_id
	if not await _is_steering_enabled(agent_id, db):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="steering is disabled for this agent",
		)
	if not (run_input_text(run_input) or run_input.attachments):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="input is required to steer a run",
		)
	if run_input.type != MessageType.USER:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="steering input must be a user message",
		)
	if run_input.splice is not None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="steering input placement belongs in parent_id",
		)
	validate_message_input(run_input)
	if any(
		mention.type == MentionableSubjectType.AGENT and mention.id != agent_id
		for mention in run_input.mentions
	):
		raise HTTPException(
			status_code=status.HTTP_501_NOT_IMPLEMENTED,
			detail="invoking another agent from steering is not implemented",
		)

	enqueued_at = datetime.now(UTC)
	draft = MessageDraft.from_request(run_input)
	if parent_id is not None:
		draft.splice = MessageSplice(parent_id=parent_id)
	draft.metadata.update(
		{
			"steering_state": "queued",
			"run_id": str(run_id),
			"agent_id": str(agent_id),
			STEERING_ENQUEUED_AT_KEY: enqueued_at.isoformat(),
		}
	)
	if client_steering_id is not None:
		draft.metadata[CLIENT_STEERING_ID_KEY] = client_steering_id
	written = await create_message(
		thread_id,
		draft,
		db,
		principal,
		# intentionally NOT passing origin_session_id: the originating client
		# needs to receive the message.created event since the /steer http
		# response races the WS event for tree updates.
		origin_session_id=None,
		# the row exists so clients can render the queued message, but the
		# agent has not read it: it is not conversation yet, so the write must
		# not move the head. moving it and undoing that afterwards would leave
		# a window where another writer chains onto a message nobody has seen.
		advances_head=False,
		originated_resources=run_input.originated_resources,
	)
	user_msg = written.message
	user_msg_id = user_msg.id

	sdk_msg = build_steering_sdk_message(
		user_msg,
		principal_user_id=principal.user.id,
		enqueued_at=enqueued_at,
		client_steering_id=client_steering_id,
	)

	injection = QueuedSteering(message_id=user_msg_id, message=sdk_msg)
	if resolved.is_local:
		delivered = 1 if await run_inbox.enqueue(run_id, injection) else 0
	else:
		delivered = await publish_steering_command(
			run_id,
			EnqueueSteeringCommand(
				message_id=user_msg_id,
				messages=injection.messages,
				retractable=True,
				thread_id=thread_id,
				agent_id=agent_id,
			),
		)
	if delivered == 0:
		# the local inbox IS the delivery: the run that just refused this
		# message lives here. publishing would reach our own subscriber, fail
		# to enqueue again, and report success for a message it never took.
		create_background_task(
			_settle_drop(
				message_id=user_msg_id,
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
			),
			name="settle_steering_no_subscriber",
		)
		return SteeringResult(message_id=user_msg_id, state="dropped")

	create_background_task(
		broadcast_steering_event(
			event_type=EventType.RUN_STEERING_QUEUED,
			thread_id=thread_id,
			agent_id=agent_id,
			run_id=run_id,
			message_ids=[user_msg_id],
			event_at=enqueued_at,
		),
		name="broadcast_steering_queued",
	)
	return SteeringResult(message_id=user_msg_id, state="queued")


async def enqueue_resolved_invocation(
	run_id: TypeID,
	invocation_message_id: TypeID,
	principal: Principal,
	db: AsyncSession,
) -> SteeringResult:
	"""catch a run up on an invocation the SERVER already authorized.

	internal only, and deliberately unreachable from any request schema: see
	``runs.launch_invoked_run`` for why the mention gate is the untrusted
	caller's evidence rather than a universal precondition.
	"""
	resolved = await _require_invocation_run(run_id, principal, db)
	if not resolved.is_local:
		return await _publish_invocation_command(
			resolved,
			invocation_message_id,
			db,
		)
	return await _enqueue_run_invocation(
		resolved,
		invocation_message_id,
		db,
		accept_already_accepted=True,
	)


async def settle_remote_invocation(
	run_id: TypeID,
	invocation_message_id: TypeID,
	principal: Principal,
	db: AsyncSession,
) -> SteeringResult:
	"""settle one cross-worker invocation on the run-owning worker."""
	try:
		result = await enqueue_resolved_invocation(
			run_id,
			invocation_message_id,
			principal,
			db,
		)
	except HTTPException:
		result = SteeringResult(message_id=invocation_message_id, state="dropped")
	return result


async def enqueue_run_invocation(
	run_id: TypeID,
	invocation_message_id: TypeID,
	principal: Principal,
	db: AsyncSession,
) -> SteeringResult:
	"""steer a running agent with a message that already exists.

	the invocation form of steering: the caller names a persisted message
	addressed to this run's agent, and the run receives everything it has not
	read up to that message. those rows already sit in their final position,
	so nothing is written - only the agent's own view moves.

	unlike the text form this is not gated on the agent's steering feature:
	being addressed in a conversation IS the invocation.
	"""
	resolved = await _require_invocation_run(run_id, principal, db)
	thread_id = require_steerable_thread(resolved)
	if not await message_mentions_agent(
		db, thread_id, invocation_message_id, resolved.agent_id
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="message does not mention this run's agent",
		)
	if not resolved.is_local:
		return await _publish_invocation_command(
			resolved,
			invocation_message_id,
			db,
		)
	return await _enqueue_run_invocation(
		resolved,
		invocation_message_id,
		db,
	)


async def _publish_invocation_command(
	resolved: ResolvedRun,
	invocation_message_id: TypeID,
	db: AsyncSession,
) -> SteeringResult:
	"""route one invocation to the worker that owns the run.

	the container is checked here rather than on the far side: a mention from
	a different conversation is the caller's error, and it deserves a 409
	instead of a command that settles as silently dropped.
	"""
	thread_id = require_steerable_thread(resolved)
	container_root_id = await branch_root_id(db, thread_id, invocation_message_id)
	if not same_container(resolved.container_root_id, container_root_id):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="message belongs to a different conversation than this run",
		)
	delivered = await publish_steering_command(
		resolved.run_id,
		InvocationSteeringCommand(
			message_id=invocation_message_id,
			thread_id=thread_id,
			agent_id=resolved.agent_id,
		),
	)
	return SteeringResult(
		message_id=invocation_message_id,
		state="queued" if delivered > 0 else "dropped",
	)


async def _require_invocation_run(
	run_id: TypeID,
	principal: Principal,
	db: AsyncSession,
) -> ResolvedRun:
	"""resolve one accessible persisted run for invocation catch-up."""
	resolved = await resolve_authorized_run(
		run_id,
		principal,
		db,
		required_level=AccessLevel.EDITOR,
	)
	require_steerable_thread(resolved)
	return resolved


async def _enqueue_run_invocation(
	resolved: ResolvedRun,
	invocation_message_id: TypeID,
	db: AsyncSession,
	accept_already_accepted: bool = False,
) -> SteeringResult:
	"""enqueue catch-up after the caller resolves invocation trust policy."""
	async with keyed_lock(_catch_up_locks, _catch_up_locks_guard, resolved.run_id):
		return await _enqueue_run_invocation_locked(
			resolved,
			invocation_message_id,
			db,
			accept_already_accepted,
		)


async def _enqueue_run_invocation_locked(
	resolved: ResolvedRun,
	invocation_message_id: TypeID,
	db: AsyncSession,
	accept_already_accepted: bool,
) -> SteeringResult:
	"""hand a local run everything it has not read up to one invocation.

	the caller holds this run's catch-up lock, which is what makes the
	reserve-then-load-then-enqueue sequence atomic against a second mention:
	every early return releases the reservation it took.
	"""
	run_id = resolved.run_id
	thread_id = require_steerable_thread(resolved)
	if not resolved.conversation_bound:
		return SteeringResult(message_id=invocation_message_id, state="dropped")
	container_root_id = await branch_root_id(db, thread_id, invocation_message_id)
	if not same_container(container_root_id, resolved.container_root_id):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="message belongs to a different conversation than this run",
		)

	reservation = await run_inbox.reserve_catch_up(run_id, invocation_message_id)
	if isinstance(reservation, CatchUpAlreadyAccepted):
		if accept_already_accepted:
			return SteeringResult(
				message_id=invocation_message_id,
				state="queued",
			)
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="invocation was already accepted by this run",
		)
	if not isinstance(reservation, CatchUpReserved):
		return SteeringResult(message_id=invocation_message_id, state="dropped")

	try:
		segment = await messages_between(
			db,
			thread_id,
			reservation.previous_invocation_id,
			invocation_message_id,
		)
	except Exception as exc:
		await run_inbox.release_catch_up(run_id, reservation)
		if isinstance(exc, ValueError):
			if (
				accept_already_accepted
				and reservation.previous_invocation_id is not None
			):
				try:
					await messages_between(
						db,
						thread_id,
						invocation_message_id,
						reservation.previous_invocation_id,
					)
				except ValueError:
					pass
				else:
					return SteeringResult(
						message_id=invocation_message_id,
						state="queued",
					)
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="message is not on this run's conversation chain",
			) from exc
		raise

	# the run's own output is already in its thread; re-injecting it would make
	# the agent read its answers back as conversation.
	unseen = [
		message
		for message in segment
		if str((message.public_metadata or {}).get("run_id") or "") != str(run_id)
	]
	sdk_messages = [orm_message_to_sdk_message(message) for message in unseen]
	injection = InvocationCatchUp(
		message_id=invocation_message_id,
		messages=sdk_messages,
	)
	local_run = await run_registry.get_run(run_id)
	if local_run is None:
		await run_inbox.release_catch_up(run_id, reservation)
		return SteeringResult(message_id=invocation_message_id, state="dropped")
	accepted = await run_inbox.enqueue(run_id, injection)
	if not accepted:
		await run_inbox.release_catch_up(run_id, reservation)
		return SteeringResult(message_id=invocation_message_id, state="dropped")

	create_background_task(
		broadcast_steering_event(
			event_type=EventType.RUN_STEERING_QUEUED,
			thread_id=thread_id,
			agent_id=resolved.agent_id,
			run_id=run_id,
			message_ids=[invocation_message_id],
		),
		name="broadcast_run_invocation_queued",
	)
	return SteeringResult(message_id=invocation_message_id, state="queued")


async def drop_run_steering(
	run_id: TypeID,
	message_id: TypeID,
	principal: Principal,
	db: AsyncSession,
) -> None:
	"""drop a still-queued steering message before it reaches the agent.

	fire-and-forget at the api level: removes the message from the run's
	inbox, persists the metadata as dropped, and broadcasts the
	``run.steering.dropped`` event. clients reconcile via the broadcast.
	"""
	# the run is the usual subject, but it is in-memory and may be gone (ended,
	# evicted, or never real). the row itself is durable, so it identifies the
	# conversation when the run cannot - never skip the check just because the
	# run lookup missed.
	resolved = await find_run(run_id)
	stored_message = await db.get(MessageORM, message_id)
	if stored_message is None or str(
		stored_message.public_metadata.get("run_id") or ""
	) != str(run_id):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found",
		)
	stored_agent_id = str(stored_message.public_metadata.get("agent_id") or "")
	if resolved is None:
		# the row remembers which run wrote it, which is enough to authorize
		# the retraction and to tell the conversation it happened.
		if not stored_agent_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="run not found",
			)
		resolved = ResolvedRun(
			run_id=run_id,
			thread_id=stored_message.thread_id,
			agent_id=TypeID(stored_agent_id),
			owner_id=principal.user.id,
			persist=True,
			container_root_id=None,
			local_status=None,
		)
	thread_id = resolved.thread_id
	agent_id = resolved.agent_id
	if thread_id is None or stored_message.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found",
		)
	await authorize_run(resolved, principal, db, required_level=AccessLevel.EDITOR)

	if not resolved.is_local:
		# the run lives on another worker (or nowhere): the command bus is the
		# only way to reach it, and zero subscribers means it is unreachable
		# rather than gone.
		delivered = await publish_steering_command(
			run_id,
			DropSteeringCommand(
				message_id=message_id,
				thread_id=thread_id,
				agent_id=agent_id,
			),
		)
		if delivered == 0:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="run is unreachable",
			)
		return

	# the local inbox IS the run: publishing would loop back to our own
	# subscriber to do exactly this, one round trip later.
	if await run_inbox.drop_pending_steering(run_id, message_id):
		create_background_task(
			_settle_drop(
				message_id=message_id,
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
			),
			name="settle_steering_drop",
		)


async def _settle_failed_injection(
	message_ids: list[TypeID],
	thread_id: TypeID,
	agent_id: TypeID,
	run_id: TypeID,
) -> None:
	"""retract steering the agent read but the write could not record.

	nothing tracks these any more (they were cleared from the in-flight
	registry before the write), so without this they sit ``queued`` forever
	with no event explaining it.
	"""
	dropped = await persist_steering_state(
		message_ids,
		"dropped",
		thread_id=thread_id,
		run_id=run_id,
		only_if_current="queued",
	)
	if not dropped:
		return
	await broadcast_steering_event(
		event_type=EventType.RUN_STEERING_DROPPED,
		thread_id=thread_id,
		agent_id=agent_id,
		run_id=run_id,
		message_ids=dropped,
		event_at=datetime.now(UTC),
	)


async def _settle_drop(
	message_id: TypeID,
	thread_id: TypeID,
	agent_id: TypeID,
	run_id: TypeID,
) -> None:
	"""flip a dropped steering row, and announce it only if it moved.

	the ``queued`` guard is what makes the drop safe against a filter that
	already drained the message; broadcasting regardless would tell clients a
	message was dropped while the DB (correctly) says it was injected.
	"""
	dropped = await persist_steering_state(
		[message_id],
		"dropped",
		thread_id=thread_id,
		run_id=run_id,
		only_if_current="queued",
	)
	if not dropped:
		return
	await broadcast_steering_event(
		event_type=EventType.RUN_STEERING_DROPPED,
		thread_id=thread_id,
		agent_id=agent_id,
		run_id=run_id,
		message_ids=dropped,
	)


# low-level helpers


async def broadcast_steering_event(
	event_type: EventType,
	thread_id: TypeID,
	agent_id: TypeID,
	run_id: TypeID,
	message_ids: list[TypeID],
	parent_id: TypeID | None = None,
	event_at: datetime | None = None,
) -> None:
	"""broadcast a run.steering.{queued,injected,dropped} event.

	``message_ids`` are the persistent ids of the affected user messages so
	subscribers can correlate the event with the optimistic ghost bubble they
	already have in the local thread state.
	"""
	if event_type not in {
		EventType.RUN_STEERING_QUEUED,
		EventType.RUN_STEERING_INJECTED,
		EventType.RUN_STEERING_DROPPED,
	}:
		raise ValueError(f"not a steering event type: {event_type}")
	timestamp = event_at or datetime.now(UTC)
	data: dict[str, object] = {
		"thread_id": thread_id,
		"agent_id": agent_id,
		"run_id": run_id,
		"message_ids": [str(m) for m in message_ids],
	}
	if event_type == EventType.RUN_STEERING_QUEUED:
		data[STEERING_ENQUEUED_AT_KEY] = timestamp.isoformat()
	elif event_type == EventType.RUN_STEERING_INJECTED:
		data[STEERING_INJECTED_AT_KEY] = timestamp.isoformat()
	elif event_type == EventType.RUN_STEERING_DROPPED:
		data[STEERING_DROPPED_AT_KEY] = timestamp.isoformat()
	if parent_id is not None:
		data["parent_id"] = parent_id
	await broadcast_to_resource(
		ResourceType.THREAD,
		thread_id,
		{
			"type": event_type,
			"data": data,
			"created_at": timestamp.isoformat(),
		},
	)


async def persist_steering_state(
	message_ids: list[TypeID],
	state: PersistedSteeringState,
	thread_id: TypeID,
	run_id: TypeID,
	only_if_current: PersistedSteeringState | None = None,
) -> list[TypeID]:
	"""set ``metadata.steering_state`` on each message id.

	returns the ids actually changed, which is what a caller must broadcast:
	the guard below means "asked to change" and "did change" are different
	sets, and announcing the second is the only honest option.

	uses a fresh DB session and short transaction so it can run from any
	terminal context (cancel handler, error finalizer, SteeringFilter
	callback, /steer late-drop branch) without sharing state with the agent
	loop.

	when ``only_if_current`` is given, the update is only applied to rows
	whose current ``steering_state`` matches it. this is the race-safety
	hatch: the inject path uses ``only_if_current="queued"`` so a late
	"dropped" persist (e.g. from a slow drop after the filter already
	drained) cannot overwrite an already-injected message, and vice versa.
	"""
	if not message_ids:
		return []
	state_changed_at = datetime.now(UTC)
	changed: list[TypeID] = []
	async with async_session_local() as session:
		stmt = select(MessageORM).where(
			MessageORM.id.in_([str(m) for m in message_ids]),
			MessageORM.thread_id == thread_id,
			MessageORM.metadata_["run_id"].astext == str(run_id),
		)
		result = await session.execute(stmt)
		for msg in result.scalars().all():
			meta = msg.public_metadata
			if (
				only_if_current is not None
				and meta.get("steering_state") != only_if_current
			):
				continue
			meta["steering_state"] = state
			if state == "dropped":
				meta[STEERING_DROPPED_AT_KEY] = state_changed_at.isoformat()
			msg.set_metadata(public=meta)
			changed.append(msg.id)
		await session.commit()
	return changed


async def persist_injected_steering(
	message_ids: list[TypeID],
	parent_id: TypeID | None,
	thread_id: TypeID,
	principal: Principal,
	consumed_at: datetime | None = None,
) -> list[TypeID]:
	"""finalize queued rows at their injection point.

	queued steering messages are persisted when enqueued so clients can show
	them immediately, but their real parent is only known when the agent loop
	drains the steering inbox. this function rewrites the persisted chain to
	match what the SDK thread actually consumed: ``parent_id -> msg1 -> msg2``.
	the same rows keep their ids: ``steering_enqueued_at`` preserves authored
	time, while ``created_at`` and ``steering_injected_at`` become injection time.

	returns the ids actually injected, in chain order. rows that lost the
	``queued`` guard (a drop won the race) are not included, so a caller can
	announce exactly what happened.
	"""
	if not message_ids:
		return []
	injected_at = consumed_at or datetime.now(UTC)
	async with async_session_local() as session:
		# taken before anything is read or written: this moves rows within the
		# tree, which is the same class of edit every other writer takes it
		# for, and the head move at the end reads the chain back.
		await acquire_resource_write_lock(session, "thread", thread_id)
		thread = await session.get(Thread, thread_id)
		if thread is None:
			return []
		multi_writer = await is_multi_writer_thread(session, thread_id)
		stmt = (
			select(MessageORM)
			.where(MessageORM.id.in_([str(m) for m in message_ids]))
			.options(*message_load_options())
		)
		result = await session.execute(stmt)
		messages_by_id = {msg.id: msg for msg in result.scalars().all()}
		next_parent_id = parent_id
		injected: list[TypeID] = []
		for message_id in message_ids:
			msg = messages_by_id.get(message_id)
			if msg is None:
				continue
			meta = msg.public_metadata
			if meta.get("steering_state") != "queued":
				continue
			await apply_existing_message_splice(
				session,
				thread,
				msg,
				next_parent_id,
				principal,
				multi_writer,
			)
			msg.created_at = injected_at
			msg.updated_at = injected_at
			meta["steering_state"] = "injected"
			meta[STEERING_INJECTED_AT_KEY] = injected_at.isoformat()
			msg.set_metadata(public=meta)
			next_parent_id = message_id
			injected.append(message_id)

		events: list[Event] = []
		for message_id in injected:
			message = messages_by_id[message_id]
			event = Event(
				scope=EventScope.THREAD,
				scope_id=thread_id,
				type=EventType.MESSAGE_UPDATED,
				data=message_event_data(message),
				user_id=principal.user.id,
				thread_id=thread_id,
				message_id=message.id,
			)
			session.add(event)
			events.append(event)
		await session.commit()
		for event in events:
			await fanout_event(event)
		return injected


async def _is_steering_enabled(agent_id: TypeID | None, db: AsyncSession) -> bool:
	"""check whether the agent has steering enabled in its config.

	returns ``False`` when no agent is associated with the run, the agent
	does not exist, or the agent explicitly sets
	``config.features.steering.enabled = false``. an absent agent_id means
	there is no config to consult, so we deny rather than silently allow.
	"""
	if agent_id is None:
		return False
	agent = await db.get(Agent, str(agent_id))
	if agent is None:
		return False
	return agent.parsed_config.features.steering.enabled


async def prepare_steering[AppContextT](
	run_id: TypeID,
	sdk_agent: SDKAgent[AppContextT],
	thread_id: TypeID | None,
	agent_id: TypeID,
	principal: Principal,
	parent_id_provider: SteeringParentProvider | None = None,
	require_processed: SteeringRequireProcessed | None = None,
	advance_parent: SteeringAdvanceParent | None = None,
	ready: SteeringReady | None = None,
) -> SDKAgent[AppContextT]:
	"""set up steering for a single agent run.

	the filter is always installed: an agent that opts out of manual steering
	(rejected at ``enqueue_run_steering``) can still be addressed again in a
	shared conversation, which is an invocation rather than a tool control.
	"""

	async def _on_injected(
		injections: list[SteeringInjection],
	) -> list[SteeringInjection]:
		"""settle and return injections accepted into the model thread.

		the inbox drains as a batch, so consecutive queued steering settles as
		one write: one thread lock, one chain, one event for one drain.
		"""
		accepted: list[SteeringInjection] = []
		pending: list[QueuedSteering] = []
		for injection in injections:
			if isinstance(injection, QueuedSteering):
				pending.append(injection)
				continue
			accepted.extend(await _settle_queued_steering(list(pending)))
			pending.clear()
			if isinstance(injection, InvocationCatchUp):
				await _settle_invocation_catch_up(injection)
				accepted.append(injection)
		accepted.extend(await _settle_queued_steering(pending))
		return accepted

	async def _settle_invocation_catch_up(injection: InvocationCatchUp) -> None:
		"""advance the run to the snapshot the invocation brought it to.

		the messages are already persisted where they belong, so this only
		moves the run's own cursors: its next answer replies to this mention
		and continues from it.
		"""
		# output the run produced before this arrived answers the older
		# snapshot, so it has to land there before the cursor moves past it.
		if require_processed is not None:
			await require_processed(
				parent_id_provider() if parent_id_provider is not None else None
			)
		if advance_parent is not None:
			await advance_parent(injection.message_id)
		await run_inbox.mark_catch_up_injected(run_id, injection.message_id)
		if thread_id is not None:
			create_background_task(
				broadcast_steering_event(
					event_type=EventType.RUN_STEERING_INJECTED,
					thread_id=thread_id,
					agent_id=agent_id,
					run_id=run_id,
					message_ids=[injection.message_id],
				),
				name="broadcast_run_invocation_injected",
			)

	async def _settle_queued_steering(
		injections: list[QueuedSteering],
	) -> list[QueuedSteering]:
		"""persist and broadcast steering messages injected into the run."""
		if not injections:
			return []
		injected_at = datetime.now(UTC)
		injected_ids: list[TypeID] = []
		for injection in injections:
			msg = injection.message
			mid = get_message_id(msg)
			if mid is None:
				continue
			msg.metadata = {
				**(msg.metadata or {}),
				CREATED_AT_KEY: injected_at.isoformat(),
				STEERING_INJECTED_AT_KEY: injected_at.isoformat(),
			}
			injected_ids.append(TypeID(mid))
		if not injected_ids:
			return []
		parent_id = parent_id_provider() if parent_id_provider is not None else None
		if require_processed is not None:
			await require_processed(parent_id)
		if thread_id is None:
			return []
		try:
			injected = await persist_injected_steering(
				injected_ids,
				parent_id,
				thread_id,
				principal=principal,
				consumed_at=injected_at,
			)
		except Exception:
			# the write can fail on its own (a busy thread 409s on the write
			# lock). the rows are still `queued`, and nothing is tracking them
			# any more, so without this they would sit queued forever with no
			# event ever explaining it.
			logger.exception(
				"failed to persist injected steering",
				extra={"run_id": str(run_id), "thread_id": str(thread_id)},
			)
			create_background_task(
				_settle_failed_injection(
					message_ids=injected_ids,
					thread_id=thread_id,
					agent_id=agent_id,
					run_id=run_id,
				),
				name="settle_steering_inject_failed",
			)
			return []
		if not injected:
			# every row lost the `queued` guard - a drop got there first, and
			# it already announced itself. saying "injected" too would send
			# clients two contradictory events for one message.
			return []
		if advance_parent is not None:
			await advance_parent(injected[-1])
		await run_inbox.mark_steering_injected(run_id, injected_ids)
		create_background_task(
			broadcast_steering_event(
				event_type=EventType.RUN_STEERING_INJECTED,
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
				message_ids=injected,
				parent_id=parent_id,
				event_at=injected_at,
			),
			name="broadcast_steering_injected",
		)
		injected_set = set(injected)
		return [
			injection
			for injection in injections
			if injection.message_id in injected_set
		]

	async def _claim_pending() -> list[SteeringInjection]:
		"""claim queued injections for the steering filter."""
		claimed: list[SteeringInjection] = []
		claimed.extend(await run_inbox.claim_inbox(run_id))
		return claimed

	steering_filter = SteeringFilter(
		claim=_claim_pending,
		on_injected=_on_injected,
		ready=ready,
	)
	return sdk_agent.model_copy(
		update={"filters": [steering_filter, *sdk_agent.filters]}
	)
