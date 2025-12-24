"""Thread and message routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.acl import AccessControlEntry
from api.models.message import Message
from api.models.thread import Thread
from api.schemas.acl import AccessControlEntry as AccessControlEntrySchema
from api.schemas.acl import AccessControlEntryCreate
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
	)


@router.get("/{thread_id}", response_model=ThreadSchema)
async def get_thread(
	thread_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Fetch a single thread with messages."""
	return await thread_service.get_thread(thread_id, db, principal=principal)


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


@router.get("/{thread_id}/messages", response_model=list[MessageSchema])
async def list_messages(
	thread_id: TypeID,
	skip: int = 0,
	limit: int = 100,
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
	)


@router.get("/{thread_id}/branch", response_model=list[MessageSchema])
async def get_current_branch(
	thread_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""Return the current root→leaf branch for this thread."""
	return await thread_service.get_current_branch(thread_id, db, principal=principal)


@router.get("/{thread_id}/tree", response_model=list[MessageSchema])
async def get_message_tree(
	thread_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""Return all messages for this thread as a flat list."""
	return await thread_service.list_message_tree(thread_id, db, principal=principal)


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


@router.post("/{thread_id}/run", response_model=ThreadRunResponse)
async def run_thread(
	thread_id: TypeID,
	req: ThreadRunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ThreadRunResponse:
	"""run a thread and persist all messages produced by the sdk."""
	user_message, created = await thread_service.run_thread(
		thread_id,
		db,
		principal=principal,
		agent_id=req.agent_id,
		model_id=req.model_id,
		model=req.model,
		input=req.input,
		temperature=req.temperature,
		max_tokens=req.max_tokens,
	)

	return ThreadRunResponse(
		thread_id=thread_id,
		user_message=MessageSchema.model_validate(user_message)
		if user_message is not None
		else None,
		messages=[MessageSchema.model_validate(m) for m in created],
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
