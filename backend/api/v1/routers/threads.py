"""Thread and message routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.core.database import get_db
from api.models.acl import AccessControlEntry
from api.models.event import Event
from api.models.message import Message
from api.models.thread import Thread
from api.schemas.acl import AccessControlEntry as AccessControlEntrySchema
from api.schemas.acl import AccessControlEntryCreate
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventsByMessageIDsRequest
from api.schemas.message import Message as MessageSchema
from api.schemas.message import MessageCreate
from api.schemas.runs import ThreadRunRequest, ThreadRunResponse
from api.schemas.thread import (
	Thread as ThreadSchema,
)
from api.schemas.thread import (
	ThreadCreate,
	ThreadSwitchRequest,
	ThreadSwitchResponse,
	ThreadUpdate,
)
from api.v1.service import acl as acl_service
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.chat import run_thread as chat_run_thread
from api.v1.service.chat import run_thread_stream as chat_run_thread_stream
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/threads", tags=["threads"])


@router.post("", response_model=ThreadSchema, status_code=status.HTTP_201_CREATED)
async def create_thread(
	thread_in: ThreadCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Create a new thread."""
	return await thread_service.create_thread(thread_in, db, principal=principal)


@router.get("", response_model=list[ThreadSchema])
async def list_threads(
	owner_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 20,
	include_hidden: bool = False,
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
		include_hidden=include_hidden,
	)


@router.get("/{thread_id}", response_model=ThreadSchema)
async def get_thread(
	thread_id: TypeID,
	include_hidden: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Fetch a single thread with messages."""
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
) -> Thread:
	"""Update thread metadata."""
	return await thread_service.update_thread(
		thread_id,
		thread_in,
		db,
		principal=principal,
	)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
	thread_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""Delete a thread."""
	await thread_service.delete_thread(thread_id, db, principal=principal)


@router.get("/{thread_id}/messages", response_model=list[MessageSchema])
async def list_messages(
	thread_id: TypeID,
	skip: int = 0,
	limit: int = 100,
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
) -> Message:
	"""Append a message to a thread."""
	return await thread_service.create_message(
		thread_id,
		message_in,
		db,
		principal=principal,
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
	)


@router.post("/{thread_id}/run", response_model=ThreadRunResponse)
async def run_thread(
	thread_id: TypeID,
	req: ThreadRunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ThreadRunResponse:
	"""run a thread with an agent and persist all messages produced."""
	result = await chat_run_thread(
		thread_id,
		req.agent_id,
		db,
		principal,
		input=req.input,
	)

	return ThreadRunResponse(
		thread_id=thread_id,
		user_message=MessageSchema.model_validate(result.user_message)
		if result.user_message is not None
		else None,
		messages=[MessageSchema.model_validate(m) for m in result.produced_messages],
	)


@router.post("/{thread_id}/run/stream")
async def run_thread_stream(
	thread_id: TypeID,
	req: ThreadRunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""stream a thread run via sse events."""
	stream = chat_run_thread_stream(
		thread_id,
		req.agent_id,
		db,
		principal,
		input=req.input,
	)
	return StreamingResponse(
		stream,
		media_type="text/event-stream",
		headers={
			"Cache-Control": "no-cache",
			"Connection": "keep-alive",
			"X-Accel-Buffering": "no",
		},
	)


@router.post("/{thread_id}/switch", response_model=ThreadSwitchResponse)
async def switch_branch(
	thread_id: TypeID,
	req: ThreadSwitchRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ThreadSwitchResponse:
	"""Switch the active branch to the subtree rooted at message_id."""
	thread = await thread_service.switch_branch(
		thread_id,
		req.message_id,
		db,
		principal=principal,
	)
	return ThreadSwitchResponse(ok=True, current_message_id=thread.current_message_id)


@router.get("/{thread_id}/acl", response_model=list[AccessControlEntrySchema])
async def list_thread_acl(
	thread_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessControlEntry]:
	"""List acl entries for a thread."""
	return await acl_service.list_thread_acl(thread_id, db, principal=principal)


@router.put("/{thread_id}/acl", response_model=list[AccessControlEntrySchema])
async def set_thread_acl(
	thread_id: TypeID,
	entries: list[AccessControlEntryCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessControlEntry]:
	"""Replace acl entries for a thread."""
	return await acl_service.set_thread_acl(thread_id, entries, db, principal=principal)
