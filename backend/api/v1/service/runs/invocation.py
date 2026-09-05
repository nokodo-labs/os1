"""posting a message and running the agents its mentions invoke.

this layer owns both halves: writing a message is a thread concern, answering
one is a run concern, and something above the two has to sequence them. it
lives with runs because runs already depend on threads, so the dependency only
ever points one way.

nothing here is client-instructed. a client asking an agent to run says so
through a run; the only thing that starts a run from a WRITE is an addressed
agent whose ``invoke_on_mention`` opted it in. that indirection is what lets a
client which cannot express a separate invoke action still get an answer.

the server owns that invocation rather than the client because a client can
only ask-then-act: two of them, or one racing a run's own shutdown, would
either start a second run for the same agent or drop the invocation entirely.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.local_tasks import create_background_task
from api.models.message import Message
from api.schemas.message import ResourceAttachment
from api.v1.service.authentication import Principal
from api.v1.service.runs.bus import RunBusUnavailableError, RunSlotContendedError
from api.v1.service.runs.failures import RunFailureReason, broadcast_run_failure
from api.v1.service.runs.launch import RunStartupError, launch_invoked_run
from api.v1.service.runs.status import (
	AgentSlot,
	AwaitPendingRun,
	StartNewRun,
	SteerExistingRun,
	agent_slots,
)
from api.v1.service.runs.steering import enqueue_resolved_invocation
from api.v1.service.threads import MessageDraft
from api.v1.service.threads.messages.writes import (
	CommittedMessageWriteError,
	WrittenMessage,
	create_message_with_commit_outcome,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


_MAX_INVOCATION_ATTEMPTS = 3
"""how many times an invocation re-resolves before giving up.

each retry means a run ended in the moment between being named and being given
the message; more than a couple in a row is a dead agent, not a race.
"""

_INVOCATION_RETRY_BASE_DELAY_SECONDS = 0.05
"""base delay between invocation re-resolution attempts."""


async def create_message_and_dispatch_invocations(
	thread_id: TypeID,
	draft: MessageDraft,
	session: AsyncSession,
	principal: Principal,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
	originated_resources: list[ResourceAttachment] | None = None,
) -> Message:
	"""persist a message, then set the agents its mentions invoked answering it.

	the write decides who is invoked, under its own lock, and says so: the
	answer depends on the thread's agent roster and their per-thread
	``invoke_on_mention``, so resolving again out here would decide against a
	roster nobody was holding still, and would 4xx a message that is already
	persisted.
	"""
	try:
		written = await create_message_with_commit_outcome(
			thread_id,
			draft,
			session,
			principal=principal,
			message_id=message_id,
			origin_session_id=origin_session_id,
			originated_resources=originated_resources,
		)
	except CommittedMessageWriteError as error:
		_dispatch_invocations(
			error.written,
			thread_id,
			principal,
			origin_session_id,
		)
		raise error.cause.with_traceback(error.cause.__traceback__) from None
	_dispatch_invocations(
		written,
		thread_id,
		principal,
		origin_session_id,
	)
	return written.message


def _dispatch_invocations(
	written: WrittenMessage,
	thread_id: TypeID,
	principal: Principal,
	origin_session_id: str | None,
) -> None:
	"""dispatch the invocation decisions made by one committed write."""
	posted_id = written.message.id
	for agent_id in written.invoked_agent_ids:
		create_background_task(
			_answer_invocation(
				thread_id=thread_id,
				message_id=posted_id,
				agent_id=agent_id,
				container_root_id=written.container_root_id,
				principal=principal,
				origin_session_id=origin_session_id,
			),
			name=f"invoke-agent:{agent_id}",
		)


async def _answer_invocation(
	thread_id: TypeID,
	message_id: TypeID,
	agent_id: TypeID,
	container_root_id: TypeID | None,
	principal: Principal,
	origin_session_id: str | None,
) -> None:
	"""catch the agent's live run up on this message, or start one for it.

	an agent already answering here is one participant with one train of
	thought, so it is caught up rather than started a second time.
	"""
	# a run that ends between being named and being handed the message leaves
	# the invocation unanswered, so each attempt re-resolves rather than
	# assuming the previous answer still holds.
	reached_a_run = False
	reached_run_id: TypeID | None = None
	try:
		for attempt in range(_MAX_INVOCATION_ATTEMPTS):
			if attempt:
				await asyncio.sleep(
					_INVOCATION_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
				)
			match await agent_slots.claim(thread_id, agent_id, container_root_id):
				case AwaitPendingRun(slot=pending):
					# another invocation is mid-start for this agent: its run
					# is the one to catch up, so wait rather than starting a
					# second. bounded, because waiting forever on a slot that
					# never resolves is worse than a duplicate run.
					try:
						started_id = await agent_slots.wait(pending)
					except TimeoutError:
						logger.warning(
							"timed out waiting for another invocation to start a run",
							extra={
								"thread_id": str(thread_id),
								"agent_id": str(agent_id),
								"message_id": str(message_id),
							},
						)
						# the slot exists, so a run for this agent IS mid-start:
						# we could not hand it the message in time, which is not
						# the same as the agent never having started.
						reached_run_id = pending.run_id
						reached_a_run = True
						break
					if started_id is not None:
						reached_a_run = True
						reached_run_id = started_id
						if await _steer(thread_id, started_id, message_id, principal):
							return
				case SteerExistingRun(run_id=live_id):
					reached_a_run = True
					reached_run_id = live_id
					if await _steer(thread_id, live_id, message_id, principal):
						return
				case StartNewRun(slot=slot):
					if await _start(
						thread_id=thread_id,
						message_id=message_id,
						agent_id=agent_id,
						container_root_id=container_root_id,
						slot=slot,
						principal=principal,
						origin_session_id=origin_session_id,
					):
						return
					break
		reason = (
			RunFailureReason.NOT_DELIVERED
			if reached_a_run
			else RunFailureReason.NEVER_STARTED
		)
	except RunBusUnavailableError as exc:
		# nothing about the agent or the message is wrong, so the record says
		# "retry later" instead of blaming a run that never existed.
		logger.warning(
			"invocation could not reach the run bus",
			extra={
				"thread_id": str(thread_id),
				"agent_id": str(agent_id),
				"message_id": str(message_id),
				"operation": exc.operation,
			},
		)
		reason = RunFailureReason.UNAVAILABLE
	except RunSlotContendedError:
		# the bus answered every round and another worker won each one, so a
		# run for this agent IS being started; ours is only the message that
		# never reached it.
		logger.warning(
			"invocation lost every race for the agent's startup slot",
			extra={
				"thread_id": str(thread_id),
				"agent_id": str(agent_id),
				"message_id": str(message_id),
			},
		)
		reason = RunFailureReason.NOT_DELIVERED
	await _report_unanswered(
		thread_id,
		agent_id,
		message_id,
		reason=reason,
		run_id=reached_run_id,
	)


async def _steer(
	thread_id: TypeID,
	run_id: TypeID,
	message_id: TypeID,
	principal: Principal,
) -> bool:
	"""hand a live run the conversation it has not read yet.

	returns whether the run took it. a run that ended in the meantime has not,
	and the invocation is still owed an answer.
	"""
	try:
		async with async_session_local() as session:
			result = await enqueue_resolved_invocation(
				run_id, message_id, principal, session
			)
		return result.state != "dropped"
	except Exception:
		logger.exception(
			"failed to catch a run up on an invocation",
			extra={
				"thread_id": str(thread_id),
				"run_id": str(run_id),
				"message_id": str(message_id),
			},
		)
		return False


async def _start(
	thread_id: TypeID,
	message_id: TypeID,
	agent_id: TypeID,
	container_root_id: TypeID | None,
	slot: AgentSlot,
	principal: Principal,
	origin_session_id: str | None,
) -> bool:
	"""run the agent against the message that invoked it.

	the run id comes from the launch rather than a lookup: a run that finishes
	before we could look would read as "nobody answering", and every waiter on
	this slot would start one of its own.
	"""
	run_id: TypeID | None = None
	handled = False
	try:
		async with async_session_local() as session:
			run_id = await launch_invoked_run(
				session,
				thread_id=thread_id,
				agent_id=agent_id,
				principal=principal,
				invoking_message_id=message_id,
				origin_session_id=origin_session_id,
			)
		handled = True
	except RunStartupError as exc:
		handled = exc.run_registered
		logger.exception(
			"invoked run failed during startup",
			extra={
				"thread_id": str(thread_id),
				"agent_id": str(agent_id),
				"message_id": str(message_id),
				"run_id": str(exc.run_id),
			},
		)
	except Exception:
		logger.exception(
			"failed to start an invoked run",
			extra={
				"thread_id": str(thread_id),
				"agent_id": str(agent_id),
				"message_id": str(message_id),
			},
		)
	finally:
		# finally, not except: cancellation is a BaseException, and an
		# unreleased slot never sets `ready`, so every later invocation for
		# this agent would wait on it forever.
		await agent_slots.release(thread_id, agent_id, container_root_id, slot, run_id)
	return handled


async def _report_unanswered(
	thread_id: TypeID,
	agent_id: TypeID,
	message_id: TypeID,
	reason: RunFailureReason,
	run_id: TypeID | None = None,
) -> None:
	"""record that an agent never answered a message it was asked to.

	the request that carried the invocation has already returned, so there is
	no response left to fail and no run anyone could be watching. only a
	durable record reaches the people in the conversation - including the ones
	who were not looking when it happened.

	the caller decides ``reason``: whether a run existed at all, whether one
	existed and would not take the message, or whether we never got to ask.
	saying the agent never started when it is answering right now is a lie to
	everyone reading the thread.
	"""
	logger.warning(
		"invocation went unanswered",
		extra={
			"thread_id": str(thread_id),
			"agent_id": str(agent_id),
			"message_id": str(message_id),
			"reason": reason,
		},
	)
	await broadcast_run_failure(
		thread_id=thread_id,
		agent_id=agent_id,
		reason=reason,
		anchor_message_id=message_id,
		run_id=run_id,
	)
