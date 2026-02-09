"""Thread and message routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import StreamingResponse

from api.core.database import get_db
from api.models.access_rule import AccessRule
from api.models.agent import Agent
from api.models.event import Event
from api.models.message import Message
from api.models.model import Model
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
from api.schemas.runs import ThreadRunRequest
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
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.chat import run_agent as chat_run_agent
from api.v1.service.chat.models import (
	build_chat_model,
	resolve_chat_model,
)
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
) -> Thread:
	"""Create a new thread."""
	return await thread_service.create_thread(thread_in, db, principal=principal)


@router.get("", response_model=list[ThreadSchema])
async def list_threads(
	owner_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 20,
	sort_by: CommonSortBy | ThreadSortBy = "updated_at",
	sort_dir: SortDir = "desc",
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
		sort_by=sort_by,
		sort_dir=sort_dir,
		include_hidden=include_hidden,
	)


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
) -> Thread:
	"""Update thread metadata."""
	return await thread_service.update_thread(
		thread_id,
		thread_in,
		db,
		principal=principal,
	)


@router.post("/{thread_id}/metadata/generate", response_model=ThreadSchema)
async def generate_thread_metadata(
	thread_id: TypeID,
	req: ThreadMetadataGenerateRequest | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Generate thread title/tags using an LLM.

	When replace is false, only fills in missing metadata.
	"""
	request = req or ThreadMetadataGenerateRequest()

	if request.model_id is not None:
		chat_model = await resolve_chat_model(
			db,
			model_id=request.model_id,
		)
	else:
		stmt = (
			select(Agent)
			.options(selectinload(Agent.model).selectinload(Model.provider))
			.where(Agent.model_id.isnot(None))
			.order_by(Agent.created_at.desc())
		)
		if not principal.is_admin:
			stmt = stmt.where(resource_access_predicate(principal, ResourceType.AGENT))
		result = await db.execute(stmt)
		agent = result.scalars().first()
		if agent is None or agent.model is None:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="no agent with a configured model",
			)
		chat_model = build_chat_model(agent.model)

	updated = await thread_service.generate_thread_metadata(
		db,
		thread_id=thread_id,
		chat_model=chat_model,
		principal=principal,
		replace=request.replace,
	)
	if updated is not None:
		return updated
	return await thread_service.get_thread(thread_id, db, principal=principal)


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


@router.post("/{thread_id}/run")
async def run_thread(
	thread_id: TypeID,
	req: ThreadRunRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""stream a thread run via sse events."""
	stream = chat_run_agent(
		thread_id,
		req.agent_id,
		db,
		principal,
		input=req.input,
		parent_id=getattr(req, "parent_id", None),
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
