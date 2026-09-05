"""thread participant routes: roster membership and per-user thread state."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.thread import (
	AgentParticipantUpdate,
	ParticipantsAddRequest,
	ThreadUserStateUpdate,
)
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread_participant import (
	AgentThreadParticipant,
	ThreadUserState,
)
from api.schemas.thread_participant import (
	ThreadParticipant as ThreadParticipantSchema,
)
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.events import SessionId
from api.v1.service.threads import (
	accept_invite,
	add_agents,
	add_members,
	block_invite,
	decline_invite,
	list_participants,
	remove_agent,
	remove_member,
	update_agent_participant,
)
from api.v1.service.threads import (
	mark_thread_read as mark_thread_read_service,
)
from api.v1.service.threads import (
	update_thread_participant as update_thread_participant_service,
)
from nokodo_ai.utils.typeid import TypeID


def create_thread_participants_router(
	resolve_thread_id: Callable[[str], TypeID],
) -> APIRouter:
	"""create participant routes mounted under the threads router."""
	router = APIRouter(prefix="/{thread_id}/participants", tags=["threads"])

	def parse_thread_id(thread_id: str) -> TypeID:
		"""parse a thread id using the owning router's resolver."""
		return resolve_thread_id(thread_id)

	@router.get("", response_model=list[ThreadParticipantSchema])
	async def list_thread_participants(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> list[ThreadParticipantSchema]:
		"""list the thread roster: members (humans + groups) plus agents."""
		return await list_participants(db, principal, thread_id)

	@router.post(
		"",
		response_model=list[ThreadParticipantSchema],
		status_code=status.HTTP_201_CREATED,
	)
	async def add_thread_participants(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		req: ParticipantsAddRequest,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> list[ThreadParticipantSchema]:
		"""add user, group, and agent participants through their policies."""
		added = await add_members(
			db,
			principal,
			thread_id,
			user_ids=req.user_ids,
			group_ids=req.group_ids,
			origin_session_id=x_session_id,
		)
		added.extend(
			await add_agents(
				db,
				principal,
				thread_id,
				req.agent_ids,
				origin_session_id=x_session_id,
			)
		)
		return added

	@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
	async def remove_thread_user_participant(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		user_id: TypeID,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> None:
		"""remove a user through thread membership policy."""
		await remove_member(
			db,
			principal,
			thread_id,
			user_id=user_id,
			origin_session_id=x_session_id,
		)

	@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
	async def remove_thread_group_participant(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		group_id: TypeID,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> None:
		"""remove a group through thread membership policy."""
		await remove_member(
			db,
			principal,
			thread_id,
			group_id=group_id,
			origin_session_id=x_session_id,
		)

	@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
	async def remove_thread_agent(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		agent_id: TypeID,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> None:
		"""remove an agent's presence from the thread."""
		await remove_agent(
			db, principal, thread_id, agent_id, origin_session_id=x_session_id
		)

	@router.patch("/agents/{agent_id}", response_model=AgentThreadParticipant)
	async def update_thread_agent_participant(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		agent_id: TypeID,
		req: AgentParticipantUpdate,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> AgentThreadParticipant:
		"""update an agent's participation in this thread."""
		return await update_agent_participant(
			db,
			principal,
			thread_id,
			agent_id,
			req.invoke_on_mention,
			origin_session_id=x_session_id,
		)

	@router.patch("/users/{user_id}", response_model=ThreadUserState)
	async def update_thread_participant(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		user_id: TypeID,
		req: ThreadUserStateUpdate,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> ThreadUserState:
		"""update a user's per-thread state (mute / pin / archive)."""
		return await update_thread_participant_service(
			db,
			principal,
			thread_id,
			user_id,
			muted=req.muted,
			pinned=req.pinned,
			archived=req.archived,
		)

	@router.post("/users/{user_id}/read", response_model=ThreadUserState)
	async def mark_thread_read(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		user_id: TypeID,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> ThreadUserState:
		"""mark all messages in a thread as read for a user."""
		return await mark_thread_read_service(
			thread_id, user_id, db, principal=principal, origin_session_id=x_session_id
		)

	@router.post("/users/{user_id}/invite/accept", response_model=ThreadSchema)
	async def accept_thread_invite(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		user_id: TypeID,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> ThreadSchema:
		"""accept a pending invitation for the named user."""
		return await accept_invite(
			db, principal, thread_id, user_id, origin_session_id=x_session_id
		)

	@router.post(
		"/users/{user_id}/invite/decline",
		status_code=status.HTTP_204_NO_CONTENT,
	)
	async def decline_thread_invite(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		user_id: TypeID,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> None:
		"""decline a pending invitation for the named user."""
		await decline_invite(
			db, principal, thread_id, user_id, origin_session_id=x_session_id
		)

	@router.post(
		"/users/{user_id}/invite/block",
		status_code=status.HTTP_204_NO_CONTENT,
	)
	async def block_thread_invite(
		thread_id: Annotated[TypeID, Depends(parse_thread_id)],
		user_id: TypeID,
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
		x_session_id: SessionId = None,
	) -> None:
		"""block the initiator and decline the named user's invitation."""
		await block_invite(
			db, principal, thread_id, user_id, origin_session_id=x_session_id
		)

	return router
