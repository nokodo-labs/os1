"""Branching chat routers.

A "chat" is exposed as a thin alias over the existing Thread + Message models.
This router provides branching operations (current branch, tree, switch).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.message import Message
from api.schemas.chat import ChatSwitchRequest, ChatSwitchResponse
from api.schemas.message import Message as MessageSchema
from api.schemas.message import MessageCreate
from api.typeid import TypeID
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, get_current_principal


router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("/{chat_id}/messages", response_model=list[MessageSchema])
async def get_current_branch(
	chat_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""Return the current root→leaf branch for this chat."""
	return await thread_service.get_current_branch(chat_id, db, principal=principal)


@router.get("/{chat_id}/tree", response_model=list[MessageSchema])
async def get_message_tree(
	chat_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""Return all messages for this chat as a flat list."""
	return await thread_service.list_message_tree(chat_id, db, principal=principal)


@router.post(
	"/{chat_id}/messages",
	response_model=MessageSchema,
	status_code=status.HTTP_201_CREATED,
)
async def add_message(
	chat_id: TypeID,
	message_in: MessageCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Message:
	"""Add a message to this chat.

	If parent_id is omitted, the message is appended to the current branch head.
	"""
	return await thread_service.create_message(
		chat_id,
		message_in,
		db,
		principal=principal,
	)


@router.post("/{chat_id}/switch", response_model=ChatSwitchResponse)
async def switch_branch(
	chat_id: TypeID,
	req: ChatSwitchRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ChatSwitchResponse:
	"""Switch the active branch to the subtree rooted at message_id."""
	thread = await thread_service.switch_branch(
		chat_id,
		req.message_id,
		db,
		principal=principal,
	)
	return ChatSwitchResponse(ok=True, current_message_id=thread.current_message_id)
