"""a run's failure, recorded the way its messages are.

a run persists its outcomes. that used to mean messages and nothing else, so
``run.error`` was broadcast live and forgotten - which leaves a reloaded
conversation ending at the user's own message with no sign anything went wrong,
and leaves every other participant with no sign at all.

an error IS an outcome: when a run stops, the error is the last thing it
produced, and it is as final as a message. so a TERMINAL failure is durable,
while transient trouble inside a still-running run is not an outcome and stays
ephemeral. an INVOCATION is terminal on its own terms: a mention that never
reached its run is answered by nobody, whether or not that run is still going,
so it is recorded even against a live one.

the record is immutable: whether a failure still stands is a question about the
conversation now (did that agent answer afterwards), not a field on the event, so
a retry never rewrites history - a second failure simply appends.
"""

import logging

from api.database import async_session_local
from api.local_tasks import create_background_task
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.v1.service.events import persist_and_fanout_event
from api.v1.service.runs.access_cursors import release_thread_access_cursor
from api.v1.service.runs.contracts import (
	RunFailureReason,
	classify_failure,
	run_failure_payload,
)
from api.v1.service.runs.status import (
	RunSnapshot,
	broadcast_run_event,
	run_registry,
)
from api.v1.service.runs.steering import (
	broadcast_steering_event,
	persist_steering_state,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def broadcast_run_failure(
	thread_id: TypeID,
	agent_id: TypeID,
	reason: RunFailureReason,
	anchor_message_id: TypeID | None,
	run_id: TypeID | None,
	partial_message_id: TypeID | None = None,
) -> None:
	"""persist and fan out the end of a run that did not answer.

	durable, unlike the rest of the run lifecycle, because it is the run's
	final output. anchored to the message the agent was answering so it renders
	where it happened rather than wherever the conversation has moved on to.

	``run_id`` is None when the agent was never reached at all - the case only a
	durable record can express, since there is no run to attach an error to and
	no stream anyone could have been watching.
	"""
	data = run_failure_payload(
		thread_id=thread_id,
		agent_id=agent_id,
		reason=reason,
		run_id=run_id,
		partial_message_id=partial_message_id,
	)
	try:
		async with async_session_local() as session:
			await persist_and_fanout_event(
				session,
				event=Event(
					scope=EventScope.THREAD,
					scope_id=str(thread_id),
					type=EventType.RUN_ERROR,
					data=data,
					thread_id=str(thread_id),
					message_id=(
						str(anchor_message_id)
						if anchor_message_id is not None
						else None
					),
				),
			)
	except Exception:
		# the run already failed; losing the record must not also break the
		# terminal path that is reporting it.
		logger.exception(
			"failed to record a run failure",
			extra={
				"thread_id": str(thread_id),
				"agent_id": str(agent_id),
				"run_id": str(run_id) if run_id is not None else None,
			},
		)


async def terminate_evicted_run(run_id: TypeID) -> None:
	"""end a run the store evicted for going silent.

	the eviction itself only drops the in-memory record; everyone watching the
	thread still needs the terminal event, and any steering the run died owing
	still needs retracting. registered on the store at import time so the
	cleanup loop reaches this without the store importing this module.
	"""
	cancelled = await run_registry.cancel_run(run_id, reason="run went silent")
	if not cancelled:
		await terminate_run(run_id, reason="run went silent")


async def terminate_run(
	run_id: TypeID,
	reason: str,
	partial_message_id: TypeID | None = None,
) -> RunSnapshot | None:
	"""claim one failed run and schedule its single terminal outcome."""
	rs = await run_registry.fail_run(run_id, reason=reason)
	if rs is None:
		return None
	await release_thread_access_cursor(rs.thread_id)
	schedule_terminate_broadcast(
		thread_id=rs.thread_id,
		agent_id=rs.agent_id,
		run_id=run_id,
		error=True,
		dropped_steering=list(rs.in_flight_steering),
		failure_reason=reason,
		anchor_message_id=failure_anchor(rs),
		partial_message_id=partial_message_id,
	)
	return rs


def failure_anchor(rs: RunSnapshot | None) -> TypeID | None:
	"""where a failed run's durable record renders in the conversation."""
	if rs is None:
		return None
	return rs.anchor_message_id


def schedule_terminate_broadcast(
	thread_id: TypeID | None,
	agent_id: TypeID,
	run_id: TypeID,
	error: bool,
	dropped_steering: list[TypeID] | None = None,
	failure_reason: str | None = None,
	anchor_message_id: TypeID | None = None,
	partial_message_id: TypeID | None = None,
) -> None:
	"""fire a run.completed/run.error broadcast for a thread-bound run.

	on failure this ALSO writes the durable record, and retracts any steering
	the run died owing. every path that ends a run goes through here, so
	cancellations, provider errors, and invoked runs are covered by
	construction rather than one entry point at a time.

	no-op for ephemeral runs (no thread to fan out to).
	"""
	if thread_id is None:
		return
	if error:
		create_background_task(
			broadcast_run_failure(
				thread_id=thread_id,
				agent_id=agent_id,
				reason=classify_failure(failure_reason),
				anchor_message_id=anchor_message_id,
				run_id=run_id,
				partial_message_id=partial_message_id,
			),
			name="broadcast_run_failure",
		)
	else:
		create_background_task(
			broadcast_run_event(
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
				started=False,
			),
			name="broadcast_run_completed",
		)
	if dropped_steering:
		create_background_task(
			_retract_dropped_steering(
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
				dropped=dropped_steering,
			),
			name="broadcast_steering_dropped",
		)


async def _retract_dropped_steering(
	thread_id: TypeID,
	agent_id: TypeID,
	run_id: TypeID,
	dropped: list[TypeID],
) -> None:
	"""flip queued steering rows to dropped and say so.

	announces what actually changed: a message the filter injected just before
	the run ended keeps its ``injected`` row, and must not also be reported
	dropped.
	"""
	if not dropped:
		return
	retracted = await persist_steering_state(
		dropped,
		"dropped",
		thread_id=thread_id,
		run_id=run_id,
		only_if_current="queued",
	)
	if not retracted:
		return
	await broadcast_steering_event(
		event_type=EventType.RUN_STEERING_DROPPED,
		thread_id=thread_id,
		agent_id=agent_id,
		run_id=run_id,
		message_ids=retracted,
	)


def configure_run_failure_handlers() -> None:
	"""wire lifecycle callbacks owned by the run-failure service."""
	run_registry.on_stale_run(terminate_evicted_run)
