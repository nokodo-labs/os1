"""runs router - unified entry point for agent runs."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.schemas.runs import ActiveRunOut, RunRequest
from api.v1.service import runs as runs_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.chat import run_agent as chat_run_agent
from api.v1.service.chat.run_status import run_status_store
from api.v1.service.events import SessionId
from nokodo_ai.utils.sse import sse_response


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
		)
		return sse_response(stream)

	# ephemeral run - no thread, no persistence
	if not req.input:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="input is required for ephemeral runs",
		)

	stream = chat_run_agent(
		None,
		req.agent_id,
		principal,
		input=req.input,
		client_context=req.client_context,
		origin_session_id=x_session_id,
		persist=False,
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
			state=rs.state,
			started_at=rs.started_at,
			updated_at=rs.updated_at,
		)
		for rs in runs
	]


@router.get("/{run_id}/stream")
async def resume_run_stream(
	run_id: str,
	principal: Principal = Depends(get_current_principal),
) -> StreamingResponse:
	"""resume an active agent run's SSE stream.

	replays recorded SSE events from the run so far, then streams live
	deltas until the run completes. returns 404 if the run doesn't exist
	or has already finished.
	"""
	result = await run_status_store.subscribe(run_id)
	if result is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="run not found or already completed",
		)

	sse_log, live_queue = result

	async def _stream() -> AsyncIterator[bytes]:
		try:
			for frame in sse_log:
				yield frame
			while True:
				live_frame = await live_queue.get()
				if live_frame is None:
					return
				yield live_frame
		finally:
			await run_status_store.unsubscribe(run_id, live_queue)

	return sse_response(_stream())
