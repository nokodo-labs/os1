"""runs router - unified entry point for agent runs."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.access_rule import AccessLevel
from api.schemas.runs import (
	ActiveRunOut,
	RunRequest,
	SteerInvocationRequest,
	SteerRunRequest,
	SteerRunResponse,
)
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.events import SessionId
from api.v1.service.runs import (
	drop_run_steering,
	enqueue_run_invocation,
	enqueue_run_steering,
	launch_thread_run,
	resolve_authorized_run,
	run_registry,
	start_ephemeral_run,
	subscribe_run_stream,
	terminate_run,
)
from api.v1.service.runs.steering_bus import (
	CancelRunCommand,
	publish_steering_command,
)
from nokodo_ai.utils.sse import sse_response
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

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
		run_id = await launch_thread_run(
			db,
			thread_id=req.thread_id,
			agent_id=req.agent_id,
			principal=principal,
			input=req.input,
			splice=req.splice,
			client_context=req.client_context,
			origin_session_id=x_session_id,
			persist=req.persist,
			tool_choice=req.tool_choice,
			extra_plugins=req.extra_plugins,
			invoking_message_id=req.invoking_message_id,
		)
		return sse_response(subscribe_run_stream(run_id, principal.user.id))
	if req.splice is not None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="output placement requires a persisted thread",
		)

	# ephemeral run - no thread, no persistence. routes through the same
	# producer-task path as persisted runs so it is cancellable and
	# observable in the run registry.
	if req.input is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="input is required for ephemeral runs",
		)

	stream = await start_ephemeral_run(
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
	runs = await run_registry.get_runs_for_user(principal.user.id)
	return [
		ActiveRunOut(
			run_id=rs.run_id,
			thread_id=rs.thread_id,
			agent_id=rs.agent_id,
			user_id=rs.user_id,
			state=rs.state,
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
	# a thread-bound run is governed by its thread, so any READER may resume it.
	await resolve_authorized_run(
		run_id,
		principal,
		db,
		required_level=AccessLevel.READER,
	)
	return sse_response(subscribe_run_stream(run_id, principal.user.id))


@router.post("/{run_id}/cancel")
async def cancel_run(
	run_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
	"""cancel an active agent run."""
	resolved = await resolve_authorized_run(
		run_id,
		principal,
		db,
		required_level=AccessLevel.EDITOR,
	)
	if not resolved.is_local:
		delivered = await publish_steering_command(
			run_id,
			CancelRunCommand(reason="cancelled"),
		)
		if delivered == 0:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
			)
		return {"status": "cancelled"}

	# cancel the producer task; its CancelledError handler does fail_run +
	# broadcast. fall back to manual fail_run if no task is attached.
	cancelled = await run_registry.cancel_run(run_id)
	if not cancelled:
		await terminate_run(run_id, reason="cancelled")
	return {"status": "cancelled"}


@router.post("/{run_id}/steer")
async def steer_run(
	run_id: TypeID,
	req: SteerRunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> SteerRunResponse:
	"""put a message into a running agent loop between iterations.

	two forms, one mechanism. ``text`` sends a NEW message: it is persisted
	immediately with ``metadata.steering_state='queued'`` so the frontend can
	render an optimistic ghost bubble, and flips to ``injected`` (or
	``dropped``) as the loop drains it. ``invocation`` names a message that
	already exists in the conversation and hands the run everything it has not
	read up to that point, writing nothing.

	either way the agent sees it at the next iteration boundary, after any
	in-flight tool calls. ``dropped`` means the run ended first.
	"""
	if isinstance(req, SteerInvocationRequest):
		result = await enqueue_run_invocation(
			run_id,
			req.invoking_message_id,
			principal,
			db,
		)
	else:
		result = await enqueue_run_steering(
			run_id,
			req.input,
			req.parent_id,
			req.client_steering_id,
			principal,
			db,
		)
	return SteerRunResponse(
		message_id=result.message_id,
		state=result.state,
	)


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
