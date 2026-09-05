"""tell a thread's people that an agent answered."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent
from api.models.event_types import EventType
from api.models.message import Message
from api.models.thread_participant import ThreadParticipant
from api.permissions import ResourceType
from api.schemas.notification import NotificationPayload
from api.v1.service.authorization import list_accessible_user_ids_for_resources
from api.v1.service.notifications import create_notifications
from api.v1.service.threads.common import INVITE_PENDING, INVITE_STATUS_KEY
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_PREVIEW_LENGTH = 120
"""how much of an answer a notification body quotes."""


async def notify_agent_answer(
	thread_id: TypeID,
	agent_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
) -> None:
	"""notify a thread's people about the answer an agent just finished.

	one notification per run, for the answer rather than the run: the run is
	mechanism, and what a person wants to know is that the agent replied. an
	answer nobody can read notifies nobody, so eligibility is the thread's
	access list - whether a recipient is looking right now is the client's
	call, not ours.
	"""
	message = await session.get(Message, message_id)
	if message is None:
		return
	agent_name = await session.scalar(select(Agent.name).where(Agent.id == agent_id))
	recipient_ids = await _answer_recipient_ids(thread_id, session)
	if not recipient_ids:
		return
	preview = (message.text_content or "").strip()
	await create_notifications(
		session,
		payload=NotificationPayload(
			title=agent_name or "agent",
			body=preview[:_PREVIEW_LENGTH] or "answered",
			tag=str(thread_id),
			action_url=f"/c/{thread_id}",
			data={
				"thread_id": str(thread_id),
				"message_id": str(message_id),
				"agent_id": str(agent_id),
			},
		),
		event_type=EventType.NOTIFICATION_AGENT,
		agent_id=agent_id,
		user_ids=recipient_ids,
	)


async def _answer_recipient_ids(
	thread_id: TypeID,
	session: AsyncSession,
) -> list[TypeID]:
	"""thread members an agent's answer is worth telling.

	an agent has no user id, so nobody is excluded as the author: everyone who
	can read the thread wanted this answer, including whoever asked for it.
	"""
	accessible_ids = await list_accessible_user_ids_for_resources(
		[(ResourceType.THREAD, thread_id)], session
	)
	if not accessible_ids:
		return []
	rows = (
		await session.execute(
			select(
				ThreadParticipant.user_id,
				ThreadParticipant.muted,
				ThreadParticipant.metadata_,
			).where(
				ThreadParticipant.thread_id == thread_id,
				ThreadParticipant.user_id.is_not(None),
			)
		)
	).all()
	excluded = {
		user_id
		for user_id, muted, metadata in rows
		if muted or (metadata or {}).get(INVITE_STATUS_KEY) == INVITE_PENDING
	}
	return [uid for uid in accessible_ids if uid not in excluded]
