"""an agent's finished answer tells the thread's people about it."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.message import Message, MessageType
from api.models.notification import Notification
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import ResourceType
from api.v1.service import access_rules
from api.v1.service.runs.notify import notify_agent_answer
from api.v1.service.threads.common import INVITE_PENDING, INVITE_STATUS_KEY
from nokodo_ai.utils.typeid import TypeID, new_typeid


pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession, slug: str) -> User:
	user = User(
		email=f"{slug}@example.com",
		username=slug,
		hashed_password="password",
		is_active=True,
		is_superuser=False,
	)
	session.add(user)
	await session.commit()
	await session.refresh(user)
	return user


async def _make_thread(session: AsyncSession, owner: User) -> Thread:
	thread = Thread(owner_id=owner.id, title="answer notifications")
	session.add(thread)
	await session.commit()
	await session.refresh(thread)
	return thread


async def _make_agent(session: AsyncSession, name: str) -> Agent:
	agent = Agent(name=name)
	session.add(agent)
	await session.commit()
	await session.refresh(agent)
	return agent


async def _make_answer(
	session: AsyncSession,
	thread: Thread,
	agent: Agent,
	text: str = "here is the answer",
) -> TypeID:
	message_cls = Message.__mapper__.polymorphic_map[MessageType.ASSISTANT].class_
	message = message_cls(
		id=TypeID(new_typeid("msg")),
		thread_id=thread.id,
		type=MessageType.ASSISTANT,
		sender_agent_id=agent.id,
		content=[{"type": "text", "text": text}],
		tool_calls=[],
		citations=[],
		metadata_={},
	)
	session.add(message)
	await session.commit()
	return message.id


async def _notifications_for(session: AsyncSession, thread_id: TypeID) -> list[str]:
	rows = await session.scalars(select(Notification).order_by(Notification.created_at))
	return [
		str(row.user_id)
		for row in rows
		if str((row.data or {}).get("thread_id")) == str(thread_id)
	]


async def test_agent_answer_notifies_the_thread_reader(
	db_session: AsyncSession,
) -> None:
	"""an answer nobody was watching still lands in the inbox."""
	owner = await _make_user(db_session, "answer_notify_owner")
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "answer-notify-agent")
	message_id = await _make_answer(db_session, thread, agent)

	await notify_agent_answer(thread.id, agent.id, message_id, db_session)

	assert await _notifications_for(db_session, thread.id) == [str(owner.id)]


async def test_agent_answer_notifies_every_thread_member(
	db_session: AsyncSession,
) -> None:
	"""the agent authored it, so nobody is excluded as its author."""
	owner = await _make_user(db_session, "answer_notify_multi_owner")
	reader = await _make_user(db_session, "answer_notify_multi_reader")
	thread = await _make_thread(db_session, owner)
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		reader.id,
		db_session,
		level=AccessLevel.READER,
	)
	agent = await _make_agent(db_session, "answer-notify-multi-agent")
	message_id = await _make_answer(db_session, thread, agent)

	await notify_agent_answer(thread.id, agent.id, message_id, db_session)

	assert set(await _notifications_for(db_session, thread.id)) == {
		str(owner.id),
		str(reader.id),
	}


async def test_muted_and_pending_members_are_not_notified(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "answer_notify_muted_owner")
	muted = await _make_user(db_session, "answer_notify_muted_reader")
	invited = await _make_user(db_session, "answer_notify_pending_reader")
	thread = await _make_thread(db_session, owner)
	for member in (muted, invited):
		await access_rules.grant_user_access_unchecked(
			ResourceType.THREAD,
			thread.id,
			member.id,
			db_session,
			level=AccessLevel.READER,
		)
	db_session.add_all(
		[
			ThreadParticipant(thread_id=thread.id, user_id=muted.id, muted=True),
			ThreadParticipant(
				thread_id=thread.id,
				user_id=invited.id,
				metadata_={INVITE_STATUS_KEY: INVITE_PENDING},
			),
		]
	)
	await db_session.commit()
	agent = await _make_agent(db_session, "answer-notify-muted-agent")
	message_id = await _make_answer(db_session, thread, agent)

	await notify_agent_answer(thread.id, agent.id, message_id, db_session)

	assert await _notifications_for(db_session, thread.id) == [str(owner.id)]


async def test_answer_notification_carries_its_thread_and_message(
	db_session: AsyncSession,
) -> None:
	"""the notification points at the answer, which is what a client renders."""
	owner = await _make_user(db_session, "answer_notify_payload_owner")
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "answer-notify-payload-agent")
	message_id = await _make_answer(db_session, thread, agent, text="the answer body")

	await notify_agent_answer(thread.id, agent.id, message_id, db_session)

	notification = (
		await db_session.scalars(
			select(Notification).where(Notification.user_id == owner.id)
		)
	).one()
	assert notification.title == "answer-notify-payload-agent"
	assert notification.body == "the answer body"
	assert notification.data["thread_id"] == str(thread.id)
	assert notification.data["message_id"] == str(message_id)
	assert notification.action_url == f"/c/{thread.id}"


async def test_a_vanished_answer_notifies_nobody(db_session: AsyncSession) -> None:
	owner = await _make_user(db_session, "answer_notify_missing_owner")
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "answer-notify-missing-agent")

	await notify_agent_answer(
		thread.id,
		agent.id,
		TypeID(new_typeid("msg")),
		db_session,
	)

	assert await _notifications_for(db_session, thread.id) == []
