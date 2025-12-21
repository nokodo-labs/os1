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
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.typeid import TypeID
from api.v1.service import acl as acl_service
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, get_current_principal


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
