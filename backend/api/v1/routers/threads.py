"""thread and message routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.access_rule import AccessLevel
from api.models.event import Event
from api.models.message import Message
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventsByMessageIDsRequest
from api.schemas.message import Message as MessageSchema
from api.schemas.message import MessageCreate, MessageUpdate
from api.schemas.runs import (
	ThreadCreateAndRunRequest,
)
from api.schemas.search import Page, SearchMode, SearchParams
from api.schemas.sorting import CommonSortBy, SortDir
from api.schemas.thread import (
	Thread as ThreadSchema,
)
from api.schemas.thread import (
	ThreadCreate,
	ThreadListFilters,
	ThreadMaintenanceRunRequest,
	ThreadSearchFilters,
	ThreadSortBy,
	ThreadSwitchRequest,
	ThreadSwitchResponse,
	ThreadUpdate,
)
from api.schemas.thread_participant import (
	ThreadParticipant as ThreadParticipantSchema,
)
from api.schemas.thread_participant import (
	ThreadUnreadCount,
)
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.routers.thread_summaries import create_thread_summaries_router
from api.v1.service import runs as runs_service
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_admin, require_thread_access
from api.v1.service.events import SessionId
from api.v1.tasks.threads import run_thread_maintenance_backfill_sweep
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.sse import sse_response
from nokodo_ai.utils.typeid import TypeID, assert_typeid


router = APIRouter(prefix="/threads", tags=["threads"])


def resolve_thread_id(thread_id: str) -> TypeID:
	try:
		return TypeID(assert_typeid(thread_id))
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="thread not found",
		) from exc


ThreadIDPath = Annotated[TypeID, Depends(resolve_thread_id)]

router.include_router(
	create_resource_access_router(
		ResourceType.THREAD,
		"thread_id",
		resolve_resource_id=resolve_thread_id,
	)
)
router.include_router(create_thread_summaries_router(resolve_thread_id))


@router.post("", response_model=ThreadSchema, status_code=status.HTTP_201_CREATED)
async def create_thread(
	thread_in: ThreadCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Thread:
	"""create a new thread."""
	return await thread_service.create_thread(
		thread_in, db, principal=principal, origin_session_id=x_session_id
	)


@router.post("/create_and_run")
async def create_and_run(
	req: ThreadCreateAndRunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> StreamingResponse:
	"""create a thread and immediately start an agent run, all via one SSE stream.

	the first event is ``thread_created`` with the full thread payload so the
	client can capture the thread id. subsequent events are the normal run
	events (message_created, delta, done).
	"""
	if not req.stream:
		raise HTTPException(
			status_code=status.HTTP_501_NOT_IMPLEMENTED,
			detail="non-streaming runs are not yet implemented",
		)

	if not req.input or (not req.input.text and not req.input.attachments):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="input is required when creating a new thread",
		)

	stream = await runs_service.create_thread_and_run_stream(
		db,
		principal=principal,
		agent_id=req.agent_id,
		input=req.input,
		thread_id=req.thread_id,
		is_temporary=req.is_temporary,
		tags=req.tags,
		project_ids=req.project_ids,
		client_context=req.client_context,
		origin_session_id=x_session_id,
		tool_choice=req.tool_choice,
		extra_plugins=req.extra_plugins,
	)
	return sse_response(stream)


@router.get("", response_model=list[ThreadSchema])
async def list_threads(
	filters: Annotated[ThreadListFilters, Depends()],
	skip: int = 0,
	limit: int = 20,
	sort_by: ThreadSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Thread]:
	"""list threads optionally filtered by owner."""
	return await thread_service.list_threads(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/count", response_model=int)
async def count_threads(
	filters: Annotated[ThreadListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count threads matching the list filters."""
	return await thread_service.count_threads(
		db,
		principal=principal,
		filters=filters,
	)


@router.get("/search", response_model=Page[ThreadSchema])
async def search_threads(
	filters: Annotated[ThreadSearchFilters, Depends()],
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	offset: int = Query(default=0, ge=0),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Page[ThreadSchema]:
	"""search threads returning ranked thread objects."""
	scored = await thread_service.search_threads(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=[ThreadSchema.model_validate(hit.item) for hit in scored[:limit]],
		has_more=len(scored) > limit,
	)


@router.post("/revectorize")
async def revectorize_threads(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all threads into qdrant. admin only."""
	require_admin(principal)
	count = await thread_service.vectorize_all_threads(db)
	return {"vectorized": count}


@router.post("/maintenance-backfill/run")
async def run_thread_maintenance_backfill(
	batch_size: Annotated[int | None, Query(ge=1, le=200)] = None,
	max_lookback_days: Annotated[int | None, Query(ge=1, le=365)] = None,
	min_inactivity_hours: Annotated[int | None, Query(ge=1, le=24 * 30)] = None,
	principal: Principal = Depends(get_current_principal),
) -> JSONObject:
	"""manually run one batch of the retroactive thread maintenance sweep.

	admin-only. this intentionally ignores the scheduled backfill enabled flag
	so admins can spot-check the sweep without leaving the periodic schedule on.
	"""
	require_admin(principal)
	return await run_thread_maintenance_backfill_sweep(
		batch_size=batch_size,
		max_lookback_days=max_lookback_days,
		min_inactivity_hours=min_inactivity_hours,
		respect_enabled=False,
	)


@router.get("/unread-counts", response_model=list[ThreadUnreadCount])
async def get_unread_counts(
	thread_ids: list[TypeID] | None = Query(None, alias="thread_id"),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ThreadUnreadCount]:
	"""return unread message counts for the current user's threads."""
	counts = await thread_service.get_unread_counts(
		db, principal=principal, thread_ids=thread_ids
	)
	return [
		ThreadUnreadCount(thread_id=tid, unread_count=count)
		for tid, count in counts.items()
	]


@router.get("/{thread_id}", response_model=ThreadSchema)
async def get_thread(
	thread_id: ThreadIDPath,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ThreadSchema:
	"""fetch a single thread."""
	return await thread_service.get_thread_payload(
		thread_id,
		db,
		principal=principal,
		include_hidden=include_hidden,
	)


@router.patch("/{thread_id}", response_model=ThreadSchema)
async def update_thread(
	thread_id: ThreadIDPath,
	thread_in: ThreadUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Thread:
	"""update thread metadata."""
	return await thread_service.update_thread(
		thread_id,
		thread_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post("/{thread_id}/maintenance/run", response_model=ThreadSchema)
async def run_thread_maintenance(
	thread_id: ThreadIDPath,
	req: ThreadMaintenanceRunRequest | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Thread:
	"""generate thread title, tags, and catalog summary using maintenance.

	uses the thread maintenance task model configured in settings. when replace is
	false, only fills in missing metadata, while still refreshing a stale or
	missing catalog summary.
	"""
	request = req or ThreadMaintenanceRunRequest()
	await require_thread_access(
		thread_id,
		db,
		principal,
		required_level=AccessLevel.ADMIN,
	)
	await thread_service.maintain_thread_metadata(
		thread_id,
		db,
		principal=principal,
		replace_metadata=request.replace_metadata,
		origin_session_id=x_session_id,
	)
	await db.flush()
	return await thread_service.get_thread(thread_id, db, principal=principal)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
	thread_id: ThreadIDPath,
	permanent: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a thread. pass permanent=true (admin only) to hard-delete."""
	await thread_service.delete_thread(
		thread_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
		permanent=permanent,
	)


@router.post("/{thread_id}/restore", response_model=ThreadSchema)
async def restore_thread(
	thread_id: ThreadIDPath,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Thread:
	"""restore a soft-deleted thread. admin only."""
	return await thread_service.restore_thread(
		thread_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("/{thread_id}/messages", response_model=list[MessageSchema])
async def list_messages(
	thread_id: ThreadIDPath,
	skip: int = 0,
	limit: int = 100,
	sort_by: CommonSortBy = "created_at",
	sort_dir: SortDir = "desc",
	group_task_runs: bool = True,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""list messages within a thread."""
	return await thread_service.list_messages(
		thread_id,
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		group_task_runs=group_task_runs,
		include_hidden=include_hidden,
	)


@router.post(
	"/{thread_id}/events/by-message-ids",
	response_model=list[EventSchema],
)
async def list_events_for_message_ids(
	thread_id: ThreadIDPath,
	req: EventsByMessageIDsRequest,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Event]:
	"""list events associated with specific messages in this thread."""
	return await thread_service.list_events_for_message_ids(
		thread_id,
		req.message_ids,
		db,
		principal=principal,
		include_hidden=include_hidden,
	)


@router.get("/{thread_id}/branch", response_model=list[MessageSchema])
async def get_current_branch(
	thread_id: ThreadIDPath,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""return the current root→leaf branch for this thread."""
	return await thread_service.get_current_branch(
		thread_id,
		db,
		principal=principal,
		include_hidden=include_hidden,
	)


@router.get("/{thread_id}/tree", response_model=list[MessageSchema])
async def get_message_tree(
	thread_id: ThreadIDPath,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""return all messages for this thread as a flat list."""
	return await thread_service.list_message_tree(
		thread_id,
		db,
		principal=principal,
		include_hidden=include_hidden,
	)


@router.post(
	"/{thread_id}/messages",
	response_model=MessageSchema,
	status_code=status.HTTP_201_CREATED,
)
async def create_message(
	thread_id: ThreadIDPath,
	message_in: MessageCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Message:
	"""append a message to a thread."""
	return await thread_service.create_message(
		thread_id,
		message_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.patch(
	"/{thread_id}/messages/{message_id}",
	response_model=MessageSchema,
)
async def update_user_message(
	thread_id: ThreadIDPath,
	message_id: TypeID,
	message_in: MessageUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Message:
	"""update a user message's content in place."""
	return await thread_service.update_user_message(
		thread_id,
		message_id,
		message_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete(
	"/{thread_id}/messages/{message_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_message_turn(
	thread_id: ThreadIDPath,
	message_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a user message and its generated response(s).

	this deletes the user message and all subsequent messages on the active
	branch until (but not including) the next user message, if any.
	"""
	await thread_service.delete_user_message_turn(
		thread_id,
		message_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post("/{thread_id}/switch", response_model=ThreadSwitchResponse)
async def switch_branch(
	thread_id: ThreadIDPath,
	req: ThreadSwitchRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ThreadSwitchResponse:
	"""switch the active branch to the subtree rooted at message_id."""
	thread = await thread_service.switch_branch(
		thread_id,
		req.message_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return ThreadSwitchResponse(ok=True, current_message_id=thread.current_message_id)


@router.post(
	"/{thread_id}/read",
	response_model=ThreadParticipantSchema,
)
async def mark_thread_read(
	thread_id: ThreadIDPath,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ThreadParticipantSchema:
	"""mark all messages in a thread as read for the current user."""
	participant = await thread_service.mark_thread_read(
		thread_id, db, principal=principal, origin_session_id=x_session_id
	)
	return ThreadParticipantSchema.model_validate(participant)
