"""agent presence in a thread.

agents are participants (recorded as thread_participants presence rows), not ACL
subjects: invoking an agent is gated by access to the agent, not by membership.
this module owns adding/removing an agent's presence, its per-thread
invoke-on-mention override, and the durable presence events that render inline.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.permissions import ResourceType
from api.schemas.agent import AgentSummary
from api.schemas.thread_participant import (
	AgentThreadParticipant,
)
from api.schemas.thread_participant import (
	ThreadParticipant as ThreadParticipantOut,
)
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	require_resource_access,
	require_thread_access,
)
from api.v1.service.events import persist_and_fanout_event
from api.v1.service.threads.common import (
	emit_thread_updated,
	thread_head_id,
)
from api.v1.service.threads.user_state import ensure_participant, get_thread_participant
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


async def _emit_agent_event(
	session: AsyncSession,
	thread_id: TypeID,
	principal: Principal,
	event_type: EventType,
	agent_id: TypeID,
	agent_name: str,
	origin_session_id: str | None = None,
) -> None:
	"""persist + fan out a durable agent-presence event anchored to the head.

	agents are participants (not ACL subjects), so add/remove rides the
	thread.participants.* types with ``kind == "agent"``. anchoring to the head
	gives it a message_id, which is the sole signal that makes it render inline
	via ``MessageEventFilter``. it is never stored as a ``Message``.
	"""
	anchor = await thread_head_id(session, thread_id)
	actor_name = principal.subject.display_name or principal.subject.username
	data: JSONObject = {
		"thread_id": str(thread_id),
		"actor_user_id": principal.user.id,
		"actor_name": actor_name,
		"kind": "agent",
		"agent_id": str(agent_id),
		"agent_name": agent_name,
	}
	await persist_and_fanout_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=event_type,
			data=data,
			user_id=principal.user.id,
			thread_id=str(thread_id),
			message_id=anchor,
		),
		origin_session_id=origin_session_id,
	)


async def add_agents(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	agent_ids: list[TypeID],
	origin_session_id: str | None = None,
) -> list[ThreadParticipantOut]:
	"""add agent participants to a thread (EDITOR + READER on each agent)."""
	if not agent_ids:
		return []
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.EDITOR
	)
	agents: list[Agent] = []
	for agent_id in agent_ids:
		await require_resource_access(
			agent_id,
			session,
			principal,
			ResourceType.AGENT,
			required_level=AccessLevel.READER,
		)
		agent = await session.get(Agent, agent_id)
		if agent is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND, detail="agent not found"
			)
		agents.append(agent)
	for agent in agents:
		await ensure_participant(thread_id, session, agent_id=agent.id)
	await session.flush()
	for agent in agents:
		await _emit_agent_event(
			session,
			thread_id,
			principal,
			EventType.THREAD_PARTICIPANT_ADDED,
			agent_id=agent.id,
			agent_name=agent.name,
			origin_session_id=origin_session_id,
		)
	await emit_thread_updated(
		session, thread_id, principal, origin_session_id=origin_session_id
	)
	return [
		AgentThreadParticipant(
			id=agent.id,
			thread_id=thread_id,
			agent=AgentSummary.model_validate(agent),
		)
		for agent in agents
	]


async def remove_agent(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
	origin_session_id: str | None = None,
) -> None:
	"""remove an agent participant from a thread."""
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.EDITOR
	)
	participant = await get_thread_participant(session, thread_id, agent_id=agent_id)
	if participant is None:
		return
	agent = await session.get(Agent, agent_id)
	await session.delete(participant)
	await session.flush()
	await _emit_agent_event(
		session,
		thread_id,
		principal,
		EventType.THREAD_PARTICIPANT_REMOVED,
		agent_id=agent_id,
		agent_name=agent.name if agent is not None else "an assistant",
		origin_session_id=origin_session_id,
	)
	await emit_thread_updated(
		session, thread_id, principal, origin_session_id=origin_session_id
	)


async def update_agent_participant(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	agent_id: TypeID,
	invoke_on_mention: bool | None,
	origin_session_id: str | None = None,
) -> AgentThreadParticipant:
	"""override whether addressing this agent HERE also asks it to answer.

	``None`` drops the override, so the agent's own default applies again.
	"""
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.EDITOR
	)
	participant = await get_thread_participant(session, thread_id, agent_id=agent_id)
	if participant is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="agent is not a participant of this thread",
		)
	participant.invoke_on_mention = invoke_on_mention
	await session.flush()
	agent = await session.get(Agent, agent_id)
	if agent is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="agent not found"
		)
	await emit_thread_updated(
		session, thread_id, principal, origin_session_id=origin_session_id
	)
	return AgentThreadParticipant(
		id=agent.id,
		thread_id=thread_id,
		agent=AgentSummary.model_validate(agent),
		invoke_on_mention=participant.invoke_on_mention,
	)
