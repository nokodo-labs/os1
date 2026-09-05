"""thread and message routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.access_rule import AccessLevel
from api.permissions import ActionPermission, ResourceType
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventsByMessageIDsRequest
from api.schemas.message import Message as MessageSchema
from api.schemas.message import (
	MessageCreate,
	MessageUpdate,
)
from api.schemas.runs import (
	ThreadCreateAndRunRequest,
)
from api.schemas.search import CursorPage, Page, SearchMode, SearchParams
from api.schemas.sorting import CommonSortBy, SortDir
from api.schemas.thread import (
	BranchPageOut,
	SiblingBranchCountOut,
	ThreadCreate,
	ThreadListFilters,
	ThreadMaintenanceRunRequest,
	ThreadSearchFilters,
	ThreadSortBy,
	ThreadSwitchRequest,
	ThreadSwitchResponse,
	ThreadUpdate,
)
from api.schemas.thread import (
	Thread as ThreadSchema,
)
from api.schemas.thread_participant import (
	ThreadUnreadCount,
)
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.routers.thread_participants import create_thread_participants_router
from api.v1.routers.thread_passages import create_thread_passages_router
from api.v1.routers.thread_summaries import create_thread_summaries_router
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import (
	project_private,
	require_permission,
	require_thread_access,
)
from api.v1.service.chat.messages import validate_message_input
from api.v1.service.chat.thread_maintenance import (
	maintain_thread_metadata,
	run_thread_maintenance_backfill_sweep,
)
from api.v1.service.events import SessionId
from api.v1.service.resource_origins.deletion import (
	delete_thread_with_originated_resources,
	delete_user_message_turn_with_originated_resources,
)
from api.v1.service.runs import (
	create_message_and_dispatch_invocations,
	create_thread_and_run_stream,
)
from api.v1.service.threads import (
	MessageDraft,
	get_thread_payload,
	list_message_siblings,
	list_message_tree,
	message_payloads,
	reconcile_thread_content_vectors,
	thread_payloads,
	vectorize_threads,
)
from api.v1.service.threads import (
	count_threads as count_threads_service,
)
from api.v1.service.threads import (
	create_thread as create_thread_service,
)
from api.v1.service.threads import (
	delete_thread as delete_thread_service,
)
from api.v1.service.threads import (
	delete_user_message_turn as delete_user_message_turn_service,
)
from api.v1.service.threads import (
	get_branch_page as get_branch_page_service,
)
from api.v1.service.threads import (
	get_thread as get_thread_service,
)
from api.v1.service.threads import (
	get_unread_counts as get_unread_counts_service,
)
from api.v1.service.threads import (
	list_events_for_message_ids as list_events_for_message_ids_service,
)
from api.v1.service.threads import (
	list_messages as list_messages_service,
)
from api.v1.service.threads import (
	list_threads as list_threads_service,
)
from api.v1.service.threads import (
	restore_thread as restore_thread_service,
)
from api.v1.service.threads import (
	search_threads as search_threads_service,
)
from api.v1.service.threads import (
	switch_branch as switch_branch_service,
)
from api.v1.service.threads import (
	update_thread as update_thread_service,
)
from api.v1.service.threads import (
	update_user_message as update_user_message_service,
)
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
router.include_router(create_thread_passages_router(resolve_thread_id))
router.include_router(create_thread_participants_router(resolve_thread_id))


@router.post("", response_model=ThreadSchema, status_code=status.HTTP_201_CREATED)
async def create_thread(
	thread_in: ThreadCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ThreadSchema:
	"""create a thread of any kind.

	the shape follows the payload: no members yields a solo AI chat, one member
	a 1:1 DM (reused if one exists), several (or ``from_group_id``) a group.
	agents and a per-thread auto-reply agent can be set at creation.
	"""
	thread = await create_thread_service(
		thread_in, db, principal=principal, origin_session_id=x_session_id
	)
	return (await thread_payloads(db, [thread], principal))[0]


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
	if req.input is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="input is required when creating a new thread",
		)

	stream = await create_thread_and_run_stream(
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
	include_last_message: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ThreadSchema]:
	"""list accessible threads matching the filters.

	the listing is principal-agnostic beyond access itself. per-user views are
	requested through the user-addressed state filters (``not_archived_by``,
	``invite_pending_for``, ...), each gated self-or-users:read.

	``include_last_message`` costs one extra query for the page; ask for it
	only when the rows actually render a message preview.
	"""
	threads = await list_threads_service(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)
	# thread_payloads embeds participants (batched roster resolution); plain
	# response_model serialization would drop them (scalars only).
	return await thread_payloads(
		db, threads, principal, include_last_message=include_last_message
	)


@router.get("/count", response_model=int)
async def count_threads(
	filters: Annotated[ThreadListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count threads matching the list filters (see the list endpoint)."""
	return await count_threads_service(
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
	scored = await search_threads_service(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=project_private(
			principal,
			ResourceType.THREAD,
			[ThreadSchema.model_validate(hit.item) for hit in scored[:limit]],
		),
		has_more=len(scored) > limit,
	)


@router.post("/revectorize")
async def revectorize_threads(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all thread points and due passages. threads operators only."""
	require_permission(principal, ActionPermission.THREADS_MANAGE)
	count = await vectorize_threads(db)
	reconciled = await reconcile_thread_content_vectors(db)
	return {"vectorized": count, "content_reconciled": len(reconciled)}


@router.post("/maintenance-backfill/run")
async def run_thread_maintenance_backfill(
	batch_size: Annotated[int | None, Query(ge=1, le=200)] = None,
	max_lookback_days: Annotated[int | None, Query(ge=1, le=365)] = None,
	min_inactivity_hours: Annotated[int | None, Query(ge=1, le=24 * 30)] = None,
	principal: Principal = Depends(get_current_principal),
) -> JSONObject:
	"""manually run one batch of the retroactive thread maintenance sweep.

	threads operators only. this intentionally ignores the scheduled backfill
	enabled flag so operators can spot-check the sweep without leaving the
	periodic schedule on.
	"""
	require_permission(principal, ActionPermission.THREADS_MANAGE)
	return await run_thread_maintenance_backfill_sweep(
		batch_size=batch_size,
		max_lookback_days=max_lookback_days,
		min_inactivity_hours=min_inactivity_hours,
		respect_enabled=False,
	)


@router.get("/unread-counts/{user_id}", response_model=list[ThreadUnreadCount])
async def get_unread_counts(
	user_id: TypeID,
	thread_ids: list[TypeID] | None = Query(None, alias="thread_id"),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ThreadUnreadCount]:
	"""return unread message counts for a user's threads (self or users:read).

	counts are computed against that user's own access and read cursors, not
	the caller's.
	"""
	counts = await get_unread_counts_service(
		db, principal=principal, user_id=user_id, thread_ids=thread_ids
	)
	return [
		ThreadUnreadCount(thread_id=tid, unread_count=count)
		for tid, count in counts.items()
	]


@router.get("/{thread_id}", response_model=ThreadSchema)
async def get_thread(
	thread_id: ThreadIDPath,
	include_hidden: bool = False,
	include_deleted: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ThreadSchema:
	"""fetch a single thread."""
	return await get_thread_payload(
		thread_id,
		db,
		principal=principal,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)


@router.patch("/{thread_id}", response_model=ThreadSchema)
async def update_thread(
	thread_id: ThreadIDPath,
	thread_in: ThreadUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ThreadSchema:
	"""update thread metadata."""
	thread = await update_thread_service(
		thread_id,
		thread_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return (await thread_payloads(db, [thread], principal))[0]


@router.post("/{thread_id}/maintenance/run", response_model=ThreadSchema)
async def run_thread_maintenance(
	thread_id: ThreadIDPath,
	req: ThreadMaintenanceRunRequest | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ThreadSchema:
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
	await maintain_thread_metadata(
		thread_id,
		db,
		principal=principal,
		replace_metadata=request.replace_metadata,
		origin_session_id=x_session_id,
	)
	await db.flush()
	thread = await get_thread_service(thread_id, db, principal=principal)
	return (await thread_payloads(db, [thread], principal))[0]


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
	thread_id: ThreadIDPath,
	permanent: bool = False,
	delete_originated_resources: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a thread. pass permanent=true (admin only) to hard-delete.

	resources that originated in this thread survive unless
	delete_originated_resources is true; attached resources are never deleted.
	"""
	if delete_originated_resources:
		await delete_thread_with_originated_resources(
			thread_id,
			db,
			principal=principal,
			origin_session_id=x_session_id,
			permanent=permanent,
		)
	else:
		await delete_thread_service(
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
) -> ThreadSchema:
	"""restore a soft-deleted thread. admin only."""
	thread = await restore_thread_service(
		thread_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return (await thread_payloads(db, [thread], principal))[0]


@router.get("/{thread_id}/messages", response_model=list[MessageSchema])
async def list_messages(
	thread_id: ThreadIDPath,
	skip: int = Query(default=0, ge=0),
	limit: int = Query(default=100, ge=1, le=200),
	sort_by: CommonSortBy = "created_at",
	sort_dir: SortDir = "desc",
	group_task_runs: bool = True,
	include_hidden: bool = False,
	include_deleted: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[MessageSchema]:
	"""list messages within a thread."""
	messages = await list_messages_service(
		thread_id,
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		group_task_runs=group_task_runs,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)
	return message_payloads(messages, principal)


@router.post(
	"/{thread_id}/events/by-message-ids",
	response_model=CursorPage[EventSchema],
)
async def list_events_for_message_ids(
	thread_id: ThreadIDPath,
	req: EventsByMessageIDsRequest,
	include_hidden: bool = False,
	include_deleted: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> CursorPage[EventSchema]:
	"""list events associated with specific messages in this thread."""
	page = await list_events_for_message_ids_service(
		thread_id,
		req.message_ids,
		db,
		principal=principal,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
		limit=req.limit,
		cursor=req.cursor,
	)
	return CursorPage(
		items=[EventSchema.model_validate(event) for event in page.items],
		next_cursor=page.next_cursor,
		has_more=page.has_more,
	)


@router.get("/{thread_id}/branch", response_model=BranchPageOut[MessageSchema])
async def get_branch_page(
	thread_id: ThreadIDPath,
	skip: int = Query(default=0, ge=0),
	limit: int = Query(default=50, ge=1, le=200),
	anchor_message_id: TypeID | None = None,
	before: Annotated[int | None, Query(ge=0, le=200)] = None,
	after: Annotated[int | None, Query(ge=0, le=200)] = None,
	cursor: str | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> BranchPageOut[MessageSchema]:
	"""return one page of a thread branch.

	without an anchor this pages the active branch from its newest message. an
	anchor selects the branch containing it - the active branch for a canon
	anchor, the anchor's own sub-thread chain otherwise - and returns the page
	holding the anchor, or an exact window around it via before/after. scroll
	with the returned cursors rather than skip: they survive concurrent writes.
	"""
	page = await get_branch_page_service(
		thread_id,
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		anchor_message_id=anchor_message_id,
		before=before,
		after=after,
		cursor=cursor,
	)
	return BranchPageOut(
		messages=message_payloads(page.messages, principal),
		total=page.total,
		skip=page.skip,
		has_toward_root=page.has_toward_root,
		has_toward_leaf=page.has_toward_leaf,
		siblings=message_payloads(page.siblings, principal),
		sibling_counts=[
			SiblingBranchCountOut(parent_id=item.parent_id, total=item.total)
			for item in page.sibling_counts
		],
		cursor_toward_root=page.cursor_toward_root,
		cursor_toward_leaf=page.cursor_toward_leaf,
	)


@router.get(
	"/{thread_id}/messages/{message_id}/siblings",
	response_model=list[MessageSchema],
)
async def get_message_siblings(
	thread_id: ThreadIDPath,
	message_id: TypeID,
	skip: int = Query(default=0, ge=0),
	limit: int = Query(default=50, ge=1, le=200),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[MessageSchema]:
	"""page the branches hanging off one message.

	the continuation for a message named in a branch page's
	``sibling_overflow``, which carries only the first few.
	"""
	siblings = await list_message_siblings(
		thread_id,
		message_id,
		db,
		principal=principal,
		skip=skip,
		limit=limit,
	)
	return message_payloads(siblings, principal)


@router.get("/{thread_id}/tree", response_model=list[MessageSchema])
async def get_message_tree(
	thread_id: ThreadIDPath,
	include_hidden: bool = False,
	include_deleted: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[MessageSchema]:
	"""return all messages for this thread as a flat list. threads operators only.

	unbounded: loads the entire thread in one call, so it is an operator
	debugging surface, never a client loading path - clients page.
	"""
	messages = await list_message_tree(
		thread_id,
		db,
		principal=principal,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)
	return message_payloads(messages, principal)


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
) -> MessageSchema:
	"""append a message to a thread, and run the agents it invokes."""
	validate_message_input(message_in)
	message = await create_message_and_dispatch_invocations(
		thread_id,
		MessageDraft.from_request(message_in),
		db,
		principal=principal,
		origin_session_id=x_session_id,
		originated_resources=message_in.originated_resources,
	)
	return message_payloads([message], principal)[0]


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
) -> MessageSchema:
	"""update a user message's content in place."""
	message = await update_user_message_service(
		thread_id,
		message_id,
		message_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return message_payloads([message], principal)[0]


@router.delete(
	"/{thread_id}/messages/{message_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_message_turn(
	thread_id: ThreadIDPath,
	message_id: TypeID,
	delete_originated_resources: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a user message and its generated response(s).

	this deletes the user message and all subsequent messages on the active
	branch until (but not including) the next user message, if any. resources
	that originated in those messages survive unless
	delete_originated_resources is true; attached resources are never deleted.
	"""
	if delete_originated_resources:
		await delete_user_message_turn_with_originated_resources(
			thread_id,
			message_id,
			db,
			principal=principal,
			origin_session_id=x_session_id,
		)
	else:
		await delete_user_message_turn_service(
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
	thread = await switch_branch_service(
		thread_id,
		req.message_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return ThreadSwitchResponse(ok=True, current_message_id=thread.current_message_id)
