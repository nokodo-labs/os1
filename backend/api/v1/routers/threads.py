"""Thread and message routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.access_rule import AccessRule
from api.models.event import Event
from api.models.message import Message
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessRuleCreate,
	AccessRuleResponse,
)
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventsByMessageIDsRequest
from api.schemas.message import Message as MessageSchema
from api.schemas.message import MessageCreate
from api.schemas.runs import ThreadCreateAndRunRequest
from api.schemas.search import CursorPage, SearchMode, SearchParams, SearchResultItem
from api.schemas.sorting import CommonSortBy, SortDir
from api.schemas.thread import (
	Thread as ThreadSchema,
)
from api.schemas.thread import (
	ThreadCreate,
	ThreadMetadataGenerateRequest,
	ThreadSwitchRequest,
	ThreadSwitchResponse,
	ThreadUpdate,
)
from api.v1.service import access_rules as access_rules_service
from api.v1.service import runs as runs_service
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.events import SessionId
from nokodo_ai.utils.sse import sse_response
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/threads", tags=["threads"])


ThreadSortBy = Literal[
	"last_activity_at",
	"title",
]


@router.post("", response_model=ThreadSchema, status_code=status.HTTP_201_CREATED)
async def create_thread(
	thread_in: ThreadCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Thread:
	"""Create a new thread."""
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

	if not req.input:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="input is required when creating a new thread",
		)

	stream = await runs_service.create_thread_and_run_stream(
		db,
		principal=principal,
		agent_id=req.agent_id,
		input=req.input,
		is_temporary=req.is_temporary,
		tags=req.tags,
		project_ids=req.project_ids,
		client_context=req.client_context,
		origin_session_id=x_session_id,
	)
	return sse_response(stream)


@router.get("", response_model=list[ThreadSchema])
async def list_threads(
	owner_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 20,
	sort_by: CommonSortBy | ThreadSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	include_hidden: bool = False,
	is_archived: bool | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Thread]:
	"""List threads optionally filtered by owner."""
	return await thread_service.list_threads(
		db,
		principal=principal,
		owner_id=owner_id,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		include_hidden=include_hidden,
		is_archived=is_archived,
	)


@router.get("/search", response_model=CursorPage[SearchResultItem])
async def search_threads(
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	cursor: str | None = Query(default=None),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> CursorPage[SearchResultItem]:
	"""search threads with cursor-based pagination."""
	return await thread_service.search_threads(
		q,
		db,
		principal=principal,
		limit=limit,
		cursor=cursor,
		search_params=SearchParams(mode=mode),
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


@router.get("/{thread_id}", response_model=ThreadSchema)
async def get_thread(
	thread_id: TypeID,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Fetch a single thread."""
	return await thread_service.get_thread(
		thread_id,
		db,
		principal=principal,
		include_hidden=include_hidden,
	)


@router.patch("/{thread_id}", response_model=ThreadSchema)
async def update_thread(
	thread_id: TypeID,
	thread_in: ThreadUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Thread:
	"""Update thread metadata."""
	return await thread_service.update_thread(
		thread_id,
		thread_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post("/{thread_id}/metadata/generate", response_model=ThreadSchema)
async def generate_thread_metadata(
	thread_id: TypeID,
	req: ThreadMetadataGenerateRequest | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Thread:
	"""generate thread title/tags using an LLM.

	uses the task model configured in settings (ai.tasks).
	when replace is false, only fills in missing metadata.
	"""
	request = req or ThreadMetadataGenerateRequest()
	return await thread_service.generate_thread_metadata(
		db,
		thread_id=thread_id,
		principal=principal,
		replace=request.replace,
		origin_session_id=x_session_id,
	)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
	thread_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""Delete a thread."""
	await thread_service.delete_thread(
		thread_id, db, principal=principal, origin_session_id=x_session_id
	)


@router.get("/{thread_id}/messages", response_model=list[MessageSchema])
async def list_messages(
	thread_id: TypeID,
	skip: int = 0,
	limit: int = 100,
	sort_by: CommonSortBy = "created_at",
	sort_dir: SortDir = "desc",
	group_task_runs: bool = True,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""List messages within a thread."""
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
	thread_id: TypeID,
	req: EventsByMessageIDsRequest,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Event]:
	"""List events associated with specific messages in this thread."""
	return await thread_service.list_events_for_message_ids(
		thread_id,
		req.message_ids,
		db,
		principal=principal,
		include_hidden=include_hidden,
	)


@router.get("/{thread_id}/branch", response_model=list[MessageSchema])
async def get_current_branch(
	thread_id: TypeID,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""Return the current root→leaf branch for this thread."""
	return await thread_service.get_current_branch(
		thread_id,
		db,
		principal=principal,
		include_hidden=include_hidden,
	)


@router.get("/{thread_id}/tree", response_model=list[MessageSchema])
async def get_message_tree(
	thread_id: TypeID,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""Return all messages for this thread as a flat list."""
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
	thread_id: TypeID,
	message_in: MessageCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Message:
	"""Append a message to a thread."""
	return await thread_service.create_message(
		thread_id,
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
	thread_id: TypeID,
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
	thread_id: TypeID,
	req: ThreadSwitchRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ThreadSwitchResponse:
	"""Switch the active branch to the subtree rooted at message_id."""
	thread = await thread_service.switch_branch(
		thread_id,
		req.message_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return ThreadSwitchResponse(ok=True, current_message_id=thread.current_message_id)


@router.get("/{thread_id}/access-rules", response_model=list[AccessRuleResponse])
async def list_thread_access_rules(
	thread_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""List access rules for a thread."""
	return await access_rules_service.list_access_rules(
		ResourceType.THREAD, str(thread_id), db, principal=principal
	)


@router.put("/{thread_id}/access-rules", response_model=list[AccessRuleResponse])
async def set_thread_access_rules(
	thread_id: TypeID,
	rules: list[AccessRuleCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""Replace access rules for a thread."""
	return await access_rules_service.set_access_rules(
		ResourceType.THREAD, str(thread_id), rules, db, principal=principal
	)
