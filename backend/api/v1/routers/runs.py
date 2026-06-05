"""runs router - unified entry point for agent runs."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.local_tasks import create_background_task
from api.models.access_rule import AccessLevel
from api.models.event_types import EventType
from api.schemas.runs import (
	ActiveRunOut,
	RunRequest,
	SteerRunRequest,
	SteerRunResponse,
)
from api.v1.service import runs as runs_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_thread_access
from api.v1.service.chat.run_status import broadcast_run_event, run_status_store
from api.v1.service.chat.steering import (
	broadcast_steering_event,
	drop_run_steering,
	enqueue_run_steering,
	persist_steering_state,
)
from api.v1.service.events import SessionId
from nokodo_ai.utils.sse import sse_response
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("")
async def create_run(
	req: RunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> StreamingResponse:
	"""start an agent run.

	when ``thread_id`` is present the run continues that thread (streaming).
	when omitted the run is **ephemeral** - inference only, nothing persisted.

	when ``stream`` is false a JSON response is returned instead of SSE
	(not yet implemented).
	"""
	if not req.stream:
		raise HTTPException(
			status_code=status.HTTP_501_NOT_IMPLEMENTED,
			detail="non-streaming runs are not yet implemented",
		)

	if req.thread_id is not None:
		stream = await runs_service.start_thread_run(
			db,
			thread_id=req.thread_id,
			agent_id=req.agent_id,
			principal=principal,
			input=req.input,
			parent_id=req.parent_id,
			client_context=req.client_context,
			origin_session_id=x_session_id,
			persist=req.persist,
			tool_choice=req.tool_choice,
			extra_plugins=req.extra_plugins,
		)
		return sse_response(stream)

	# ephemeral run - no thread, no persistence. routes through the same
	# producer-task path as persisted runs so it is cancellable and
	# observable in the run_status_store.
	if not req.input or (not req.input.text and not req.input.attachments):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="input is required for ephemeral runs",
		)

	stream = await runs_service.start_ephemeral_run(
		agent_id=req.agent_id,
		principal=principal,
		input=req.input,
		client_context=req.client_context,
		origin_session_id=x_session_id,
		tool_choice=req.tool_choice,
		extra_plugins=req.extra_plugins,
	)
	return sse_response(stream)


@router.get("", response_model=list[ActiveRunOut])
async def list_runs(
	principal: Principal = Depends(get_current_principal),
) -> list[ActiveRunOut]:
	"""list all in-memory runs owned by the current user."""
	runs = await run_status_store.get_runs_for_user(principal.user_id)
	return [
		ActiveRunOut(
			run_id=rs.run_id,
			thread_id=rs.thread_id,
			agent_id=rs.agent_id,
			user_id=rs.user_id,
			state=rs.state.value,
			started_at=rs.started_at,
			updated_at=rs.updated_at,
		)
		for rs in runs
	]


@router.get("/{run_id}/stream")
async def resume_run_stream(
	run_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""resume an active agent run's SSE stream.

	replays recorded SSE events from the run so far, then streams live
	deltas until the run completes. returns 404 if the run doesn't exist
	or has already finished.
	"""
	rs = await run_status_store.get_run(run_id)
	if rs is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found or already completed",
		)
	# access: thread-bound runs check thread ACL (any READER can resume);
	# ephemeral runs (no thread) are restricted to the owner.
	if rs.thread_id is not None:
		await require_thread_access(
			rs.thread_id,
			db,
			principal,
			required_level=AccessLevel.READER,
		)
	elif rs.user_id != principal.user_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found or already completed",
		)

	return sse_response(_resume_stream(run_id))


async def _resume_stream(run_id: TypeID) -> AsyncIterator[bytes]:
	"""adapt UnknownRunError to 404 while streaming subscribe_run_stream."""
	try:
		async for chunk in runs_service.subscribe_run_stream(run_id):
			yield chunk
	except runs_service.UnknownRunError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found or already completed",
		) from exc


@router.post("/{run_id}/cancel")
async def cancel_run(
	run_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
	"""cancel an active agent run."""
	rs = await run_status_store.get_run(run_id)
	if rs is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
		)
	if rs.thread_id is not None:
		await require_thread_access(
			rs.thread_id, db, principal, required_level=AccessLevel.EDITOR
		)
	elif rs.user_id != principal.user_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
		)

	# cancel the producer task; its CancelledError handler does fail_run +
	# broadcast. fall back to manual fail_run if no task is attached.
	cancelled = await run_status_store.cancel_run(run_id)
	if not cancelled:
		rs_terminated = await run_status_store.fail_run(run_id, reason="cancelled")
		# rs_terminated is None when the run completed naturally between the
		# get_run check and cancel_run / fail_run (concurrent terminal handler
		# already popped it). emit nothing in that case to avoid sending a
		# spurious run.error after run.completed.
		if rs_terminated is not None and rs.thread_id is not None:
			dropped = rs_terminated.in_flight_steering()
			create_background_task(
				broadcast_run_event(
					thread_id=rs.thread_id,
					agent_id=rs.agent_id,
					run_id=run_id,
					started=False,
					error=True,
				),
				name="broadcast_run_error_cancel_fallback",
			)
			if dropped:
				create_background_task(
					persist_steering_state(
						dropped, "dropped", only_if_current="queued"
					),
					name="persist_steering_dropped_cancel_fallback",
				)
				create_background_task(
					broadcast_steering_event(
						event_type=EventType.RUN_STEERING_DROPPED,
						thread_id=rs.thread_id,
						agent_id=rs.agent_id,
						run_id=run_id,
						message_ids=dropped,
					),
					name="broadcast_steering_dropped_cancel_fallback",
				)
	return {"status": "cancelled"}


@router.post("/{run_id}/steer")
async def steer_run(
	run_id: TypeID,
	req: SteerRunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> SteerRunResponse:
	"""inject a user message into a running agent loop between iterations.

	the message is persisted immediately with ``metadata.steering_state='queued'``
	so the frontend can render an optimistic ghost bubble. the agent loop
	drains the inbox at the next iteration boundary (after any in-flight tool
	calls), updates the message to ``steering_state='injected'``, and
	broadcasts ``run.steering.injected``.

	if the run terminates before the loop drains it, the message is marked
	``steering_state='dropped'`` and a ``run.steering.dropped`` event is
	broadcast.
	"""
	result = await enqueue_run_steering(
		run_id,
		req.input,
		req.parent_id,
		req.client_steering_id,
		principal,
		db,
	)
	return SteerRunResponse(message_id=result.message_id, state=result.state)


@router.delete(
	"/{run_id}/steer/{message_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def drop_steer(
	run_id: TypeID,
	message_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""drop a still-queued steering message before the agent injects it.

	returns 204. fire-and-forget: clients reconcile via the
	``run.steering.dropped`` event broadcast on the thread.
	"""
	await drop_run_steering(run_id, message_id, principal, db)
