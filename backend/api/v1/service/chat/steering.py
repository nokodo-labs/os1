"""run-steering service: persist + enqueue + broadcast.

extracted from the threads router so HTTP handlers stay thin and so the
same flow can be invoked from non-HTTP entry points (e.g. tests, future
internal callers).

cross-worker: ``enqueue_run_steering`` and ``drop_run_steering`` always
publish to the per-run steering channel via ``steering_bus``. the worker
that owns the run runs a subscriber that drains the channel into its
in-process inbox.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.local_tasks import create_background_task, create_inline_background_task
from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.event_types import EventType
from api.models.message import Message as MessageORM
from api.models.thread import Thread
from api.permissions import ResourceType
from api.redis import make_run_channel
from api.schemas.agent import AgentConfig
from api.schemas.runs import RunInput
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	list_accessible_user_ids,
	require_thread_access,
)
from api.v1.service.chat.filters.steering import SteeringFilter
from api.v1.service.chat.message_metadata import MESSAGE_ID_KEY, get_message_id
from api.v1.service.chat.run_status import run_status_store
from api.v1.service.chat.user_message import (
	create_run_user_message,
	resolve_run_input,
)
from api.v1.service.events import fanout_live_payload
from nokodo_ai import Agent as SDKAgent
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


SteeringState = Literal["queued", "dropped"]
SteeringParentProvider = Callable[[], TypeID | None]
SteeringParentReadyCallback = Callable[[TypeID | None], Awaitable[None]]
SteeringParentAdvancedCallback = Callable[[TypeID], None]


@dataclass(frozen=True, slots=True)
class SteeringResult:
	"""outcome of an ``enqueue_run_steering`` call."""

	message_id: TypeID
	state: SteeringState


async def enqueue_run_steering(
	run_id: TypeID,
	run_input: RunInput,
	parent_id: TypeID | None,
	principal: Principal,
	db: AsyncSession,
) -> SteeringResult:
	"""validate, persist, and enqueue a steering message for a running agent.

	on success the persisted message is returned with state=``queued`` and a
	``run.steering.queued`` event is broadcast. the owning worker (which
	may or may not be this one) handles the late-drop case via the
	in-flight terminal handlers.

	raises ``HTTPException`` for the usual auth / not-found / 422 cases so
	the router can simply ``return await enqueue_run_steering(...)``.
	"""
	rs = await run_status_store.get_run(run_id)
	if rs is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
		)
	thread_id = rs.thread_id
	if thread_id is None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="cannot steer an ephemeral run",
		)
	# verify steering is enabled on the run's agent. if disabled, the
	# SteeringFilter is never installed and queued messages would sit in
	# the inbox forever - reject early.
	if not await _is_steering_enabled(rs.agent_id, db):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="steering is disabled for this agent",
		)
	await require_thread_access(
		thread_id, db, principal, required_level=AccessLevel.EDITOR
	)
	thread = await db.get(Thread, thread_id)
	previous_current_message_id = (
		thread.current_message_id if thread is not None else None
	)
	if run_input is None or (not run_input.text and not run_input.attachment_ids):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="input is required to steer a run",
		)

	resolved = await resolve_run_input(run_input, db)
	extra_meta: JSONObject = {"steering_state": "queued", "run_id": str(run_id)}

	user_msg = await create_run_user_message(
		thread_id,
		db,
		principal=principal,
		resolved_input=resolved,
		parent_id=parent_id,
		run_id=run_id,
		# intentionally NOT passing origin_session_id: the originating client
		# needs to receive the message.created event since the /steer http
		# response races the WS event for tree updates.
		origin_session_id=None,
		extra_metadata=extra_meta,
	)
	user_msg_id = TypeID(str(user_msg.id))
	if thread is not None:
		thread.current_message_id = previous_current_message_id
		await db.commit()

	sdk_msg = SDKUserMessage(
		content=resolved,
		metadata={
			MESSAGE_ID_KEY: str(user_msg.id),
		},
	)

	# always go through the bus so the worker that owns the run picks it
	# up regardless of which worker served this http request.
	delivered = await publish_steer(
		run_id=run_id,
		message_id=user_msg_id,
		sdk_message=sdk_msg,
		thread_id=thread_id,
		agent_id=rs.agent_id,
	)

	if delivered == 0:
		# no worker is subscribed - the run terminated between the get_run
		# check above and the publish. flip the freshly-persisted message
		# to dropped so it doesn't sit "queued" forever, and emit a
		# dropped event instead of queued.
		create_background_task(
			persist_steering_state([user_msg_id], "dropped", only_if_current="queued"),
			name="persist_steering_no_subscriber",
		)
		create_background_task(
			broadcast_steering_event(
				event_type=EventType.RUN_STEERING_DROPPED,
				thread_id=thread_id,
				agent_id=rs.agent_id,
				run_id=run_id,
				message_ids=[user_msg_id],
			),
			name="broadcast_steering_no_subscriber",
		)
		return SteeringResult(message_id=user_msg_id, state="dropped")

	create_background_task(
		broadcast_steering_event(
			event_type=EventType.RUN_STEERING_QUEUED,
			thread_id=thread_id,
			agent_id=rs.agent_id,
			run_id=run_id,
			message_ids=[user_msg_id],
		),
		name="broadcast_steering_queued",
	)
	return SteeringResult(message_id=user_msg_id, state="queued")


async def drop_run_steering(
	run_id: TypeID,
	message_id: TypeID,
	principal: Principal,
	db: AsyncSession,
) -> None:
	"""drop a still-queued steering message before it reaches the agent.

	fire-and-forget at the api level: publishes a drop request to the
	owning worker, persists the message metadata as dropped, and broadcasts
	the ``run.steering.dropped`` event. clients reconcile via the broadcast.
	"""
	rs = await run_status_store.get_run(run_id)
	thread_id = rs.thread_id if rs is not None else None
	if thread_id is not None:
		await require_thread_access(
			thread_id, db, principal, required_level=AccessLevel.EDITOR
		)

	agent_id = rs.agent_id if rs is not None else None

	delivered = 0
	if rs is not None:
		delivered = await publish_drop(
			run_id=run_id,
			message_id=message_id,
			thread_id=thread_id,
			agent_id=agent_id,
		)

	if delivered > 0:
		# the owning worker's _handle_drop will run persist + broadcast
		# atomically based on whether the message was actually pending.
		return

	# no live subscriber - either the run already terminated or it was
	# never registered. flip the row defensively (only if still queued)
	# and broadcast so listening clients reconcile.
	create_background_task(
		persist_steering_state([message_id], "dropped", only_if_current="queued"),
		name="persist_steering_user_drop_no_sub",
	)
	if thread_id is not None and agent_id is not None:
		create_background_task(
			broadcast_steering_event(
				event_type=EventType.RUN_STEERING_DROPPED,
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
				message_ids=[message_id],
			),
			name="broadcast_steering_user_drop_no_sub",
		)


# low-level helpers


async def broadcast_steering_event(
	event_type: EventType,
	thread_id: TypeID,
	agent_id: TypeID,
	run_id: TypeID,
	message_ids: list[TypeID],
	parent_id: TypeID | None = None,
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
	data: dict[str, object] = {
		"thread_id": thread_id,
		"agent_id": agent_id,
		"run_id": run_id,
		"message_ids": [str(m) for m in message_ids],
	}
	if parent_id is not None:
		data["parent_id"] = parent_id
	payload: dict[str, object] = {"type": event_type, "data": data}

	async with async_session_local() as db_session:
		recipient_ids = await list_accessible_user_ids(
			ResourceType.THREAD, thread_id, db_session
		)

	if recipient_ids:
		await fanout_live_payload(payload, recipient_ids, None, False)


async def persist_steering_state(
	message_ids: list[TypeID],
	state: str,
	only_if_current: str | None = None,
) -> None:
	"""set ``metadata.steering_state`` on each message id.

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
		return
	async with async_session_local() as session:
		stmt = select(MessageORM).where(
			MessageORM.id.in_([str(m) for m in message_ids])
		)
		result = await session.execute(stmt)
		for msg in result.scalars().all():
			meta = dict(msg.metadata_ or {})
			if (
				only_if_current is not None
				and meta.get("steering_state") != only_if_current
			):
				continue
			meta["steering_state"] = state
			msg.metadata_ = meta
		await session.commit()


async def persist_injected_steering(
	message_ids: list[TypeID],
	parent_id: TypeID | None,
) -> TypeID | None:
	"""mark steering messages injected and move them to the injection point.

	queued steering messages are persisted when enqueued so clients can show
	them immediately, but their real parent is only known when the agent loop
	drains the steering inbox. this function rewrites the persisted chain to
	match what the SDK thread actually consumed: ``parent_id -> msg1 -> msg2``.
	"""
	if not message_ids:
		return None
	async with async_session_local() as session:
		stmt = select(MessageORM).where(
			MessageORM.id.in_([str(m) for m in message_ids])
		)
		result = await session.execute(stmt)
		messages_by_id = {TypeID(str(msg.id)): msg for msg in result.scalars().all()}
		next_parent_id = parent_id
		last_injected_id: TypeID | None = None
		thread_id: TypeID | None = None
		for message_id in message_ids:
			msg = messages_by_id.get(message_id)
			if msg is None:
				continue
			meta = dict(msg.metadata_ or {})
			if meta.get("steering_state") != "queued":
				continue
			msg.parent_id = next_parent_id
			meta["steering_state"] = "injected"
			msg.metadata_ = meta
			thread_id = msg.thread_id
			next_parent_id = message_id
			last_injected_id = message_id

		if thread_id is not None and last_injected_id is not None:
			thread = await session.get(Thread, thread_id)
			if thread is not None:
				thread.current_message_id = last_injected_id
		await session.commit()
		return last_injected_id


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
	agent_config: AgentConfig,
	thread_id: TypeID | None,
	agent_id: TypeID,
	parent_id_provider: SteeringParentProvider | None = None,
	wait_for_parent_persisted: SteeringParentReadyCallback | None = None,
	on_parent_advanced: SteeringParentAdvancedCallback | None = None,
) -> tuple[SDKAgent[AppContextT], asyncio.Task[None] | None]:
	"""set up steering for a single agent run.

	returns ``(agent, subscriber_task)``.  when steering is disabled by
	the agent config the original agent and ``None`` are returned.
	the caller must cancel ``subscriber_task`` in its ``finally`` block.
	"""
	if not agent_config.features.steering.enabled:
		return sdk_agent, None

	subscriber = await start_steering_subscriber(run_id)

	async def _on_steering_injected(messages: list[SDKUserMessage]) -> None:
		"""persist and broadcast steering messages injected into the run."""
		injected_ids: list[TypeID] = []
		for msg in messages:
			mid = get_message_id(msg)
			if mid is None:
				continue
			injected_ids.append(TypeID(mid))
		if not injected_ids:
			return
		parent_id = parent_id_provider() if parent_id_provider is not None else None
		if wait_for_parent_persisted is not None:
			await wait_for_parent_persisted(parent_id)
		# clear from claimed_steering so terminal handlers don't see these
		# as in-flight (and thus mistakenly report them as dropped).
		await run_status_store.mark_steering_injected(run_id, injected_ids)
		last_injected_id = await persist_injected_steering(injected_ids, parent_id)
		if last_injected_id is not None and on_parent_advanced is not None:
			on_parent_advanced(last_injected_id)
		if thread_id is not None:
			create_background_task(
				broadcast_steering_event(
					event_type=EventType.RUN_STEERING_INJECTED,
					thread_id=thread_id,
					agent_id=agent_id,
					run_id=run_id,
					message_ids=injected_ids,
					parent_id=parent_id,
				),
				name="broadcast_steering_injected",
			)

	async def _claim_pending() -> list[SDKUserMessage]:
		"""claim queued steering messages for the steering filter."""
		return await run_status_store.claim_pending_steering(run_id)

	steering_filter = SteeringFilter(
		claim=_claim_pending,
		on_injected=_on_steering_injected,
	)
	agent_with_filter = sdk_agent.model_copy(
		update={"filters": [steering_filter, *sdk_agent.filters]}
	)
	return agent_with_filter, subscriber


# cross-worker steering bus (redis pub/sub)
# channel ``nokodo-ai:run:{run_id}:steer`` carries control envelopes for a
# single run. senders fan out to whichever worker is subscribed.

_STEER_CHANNEL_SUFFIX: Final[str] = "steer"


async def publish_steer(
	run_id: TypeID,
	message_id: TypeID,
	sdk_message: SDKUserMessage,
	thread_id: TypeID,
	agent_id: TypeID,
) -> int:
	"""publish a steer envelope to the run's bus channel.

	returns the number of redis subscribers that received the envelope.
	the caller treats ``0`` as "no worker is currently handling this run"
	(run terminated or never registered) and is responsible for marking
	the persisted message as dropped + broadcasting.

	``thread_id`` and ``agent_id`` are carried inline so the owning
	worker's handler can persist + broadcast even when the run has just
	been popped from its store (race between publish and terminal handler).
	"""
	channel = make_run_channel(str(run_id), _STEER_CHANNEL_SUFFIX)
	envelope = {
		"op": "steer",
		"run_id": str(run_id),
		"message_id": str(message_id),
		"thread_id": str(thread_id),
		"agent_id": str(agent_id),
		"sdk_message": sdk_message.model_dump(mode="json"),
	}
	delivered = await channel.publish(envelope)
	if delivered == 0:
		logger.debug("steer for run %s published with no live subscribers", run_id)
	return delivered


async def publish_drop(
	run_id: TypeID,
	message_id: TypeID,
	thread_id: TypeID | None,
	agent_id: TypeID | None,
) -> int:
	"""publish a drop envelope to the run's bus channel.

	returns the number of redis subscribers that received the envelope.
	the caller treats ``0`` as "no worker is currently handling this run"
	and is responsible for the fallback persist + broadcast.

	``thread_id`` / ``agent_id`` are carried inline so the owning worker's
	handler can broadcast the dropped event even if the run is gone from
	its store by the time the message arrives.
	"""
	channel = make_run_channel(str(run_id), _STEER_CHANNEL_SUFFIX)
	envelope: dict[str, object] = {
		"op": "drop",
		"run_id": str(run_id),
		"message_id": str(message_id),
	}
	if thread_id is not None:
		envelope["thread_id"] = str(thread_id)
	if agent_id is not None:
		envelope["agent_id"] = str(agent_id)
	return await channel.publish(envelope)


async def start_steering_subscriber(run_id: TypeID) -> asyncio.Task[None]:
	"""subscribe the local worker as the owner of ``run_id``.

	returns a task handle the caller must cancel when the run terminates.
	"""
	return create_inline_background_task(
		_run_subscriber(run_id), name=f"steering_subscriber_{run_id}"
	)


async def _run_subscriber(run_id: TypeID) -> None:
	"""drain the bus channel into the local in-process inbox.

	wraps the subscribe loop in a retry with capped backoff so a
	transient redis hiccup does not silently kill steering for the rest
	of the run. exits cleanly when the task is cancelled (the agent loop
	cancels this in its ``finally``).
	"""
	channel = make_run_channel(str(run_id), _STEER_CHANNEL_SUFFIX)
	backoff = 0.5
	max_backoff = 5.0
	while True:
		try:
			async for envelope in channel.subscribe():
				op = envelope.get("op")
				if op == "steer":
					await _handle_steer(run_id, envelope)
				elif op == "drop":
					await _handle_drop(run_id, envelope)
				else:
					logger.warning("unknown steering op for run %s: %r", run_id, op)
			# subscribe() exhausted normally - rare, but reconnect.
			backoff = 0.5
		except asyncio.CancelledError:
			raise
		except Exception:
			logger.exception(
				"steering subscriber crashed for run %s, reconnecting in %.1fs",
				run_id,
				backoff,
			)
			await asyncio.sleep(backoff)
			backoff = min(backoff * 2, max_backoff)


async def _handle_steer(run_id: TypeID, envelope: dict[str, object]) -> None:
	"""decode + enqueue a steer envelope into the local inbox."""
	raw_message_id = envelope.get("message_id")
	raw_sdk = envelope.get("sdk_message")
	if not isinstance(raw_message_id, str) or not isinstance(raw_sdk, dict):
		logger.warning("malformed steer envelope for run %s", run_id)
		return
	message_id = TypeID(raw_message_id)
	sdk_msg = SDKUserMessage.model_validate(raw_sdk)
	accepted = await run_status_store.enqueue_steering(run_id, message_id, sdk_msg)
	if accepted:
		return
	# the run terminated locally between the publisher's get_run() check and
	# our handler running, OR the inbox was full. without this branch the
	# message would sit in the DB as "queued" forever (terminal handlers
	# only catch in-process pending_steering, not late-arriving redis
	# envelopes). flip it to dropped and broadcast so the UI reconciles.
	#
	# routing fields come from the envelope itself: looking them up via
	# get_run is unreliable here (the run may have been popped by the
	# concurrent terminal handler that caused the enqueue to fail).
	raw_thread_id = envelope.get("thread_id")
	raw_agent_id = envelope.get("agent_id")
	thread_id = TypeID(raw_thread_id) if isinstance(raw_thread_id, str) else None
	agent_id = TypeID(raw_agent_id) if isinstance(raw_agent_id, str) else None
	create_background_task(
		persist_steering_state([message_id], "dropped", only_if_current="queued"),
		name="persist_steering_late_drop",
	)
	if thread_id is not None and agent_id is not None:
		create_background_task(
			broadcast_steering_event(
				event_type=EventType.RUN_STEERING_DROPPED,
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
				message_ids=[message_id],
			),
			name="broadcast_steering_late_drop",
		)


async def _handle_drop(run_id: TypeID, envelope: dict[str, object]) -> None:
	"""decode + remove a queued steering message from the local inbox.

	when the drop hits a still-pending message we own here, we run the
	persist + broadcast on this worker (gated on the actual drop
	succeeding) so the row is not flipped to ``dropped`` if the filter
	already injected it. when the message is unknown locally (already
	injected, already dropped, never queued here) we do nothing - the
	originating worker only falls back to local persist when the publish
	had zero subscribers, which we are not.
	"""
	raw_message_id = envelope.get("message_id")
	if not isinstance(raw_message_id, str):
		logger.warning("malformed drop envelope for run %s", run_id)
		return
	message_id = TypeID(raw_message_id)
	dropped = await run_status_store.drop_pending_steering(run_id, message_id)
	if not dropped:
		return
	# routing fields come from the envelope so the broadcast still works
	# if the run was popped between drop_pending_steering and the lookup.
	raw_thread_id = envelope.get("thread_id")
	raw_agent_id = envelope.get("agent_id")
	thread_id = TypeID(raw_thread_id) if isinstance(raw_thread_id, str) else None
	agent_id = TypeID(raw_agent_id) if isinstance(raw_agent_id, str) else None
	create_background_task(
		persist_steering_state([message_id], "dropped", only_if_current="queued"),
		name="persist_steering_drop_owner",
	)
	if thread_id is not None and agent_id is not None:
		create_background_task(
			broadcast_steering_event(
				event_type=EventType.RUN_STEERING_DROPPED,
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
				message_ids=[message_id],
			),
			name="broadcast_steering_drop_owner",
		)
