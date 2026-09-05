"""reply anchors, addressed subjects, and mention-driven agent selection."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.group import Group
from api.models.message import Message
from api.models.message_mention import MessageMention, subject_fk_name
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import MentionableSubjectType, ResourceType
from api.schemas.message import MessageMention as MessageMentionSchema
from api.v1.service.authentication import Principal
from api.v1.service.authorization import require_resource_access
from api.v1.service.social.visibility import user_addressable_predicate
from api.v1.service.threads.tree import message_is_visible
from api.v1.service.threads.user_state import get_thread_participant
from nokodo_ai.utils.typeid import TypeID


async def resolve_reply_anchor(
	session: AsyncSession,
	thread_id: TypeID,
	reply_to_message_id: TypeID | None,
) -> TypeID | None:
	"""validate the visible message a new message answers."""
	if reply_to_message_id is None:
		return None
	anchor = await session.get(Message, reply_to_message_id)
	if anchor is None or anchor.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reply target not found in this thread",
		)
	if not await message_is_visible(session, thread_id, reply_to_message_id):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reply target not found in this thread",
		)
	return anchor.id


async def build_mention_links(
	session: AsyncSession,
	thread_id: TypeID,
	mentions: list[MessageMentionSchema],
	principal: Principal,
) -> tuple[list[MessageMention], dict[TypeID, ThreadParticipant]]:
	"""validate addressed subjects and return loaded agent participants."""
	links: list[MessageMention] = []
	agent_participants: dict[TypeID, ThreadParticipant] = {}
	for mention in mentions:
		participant = await _require_addressable(session, thread_id, mention, principal)
		if participant is not None:
			agent_participants[mention.id] = participant
		links.append(
			MessageMention(
				position=len(links),
				**{subject_fk_name(mention.type): mention.id},
			)
		)
	return links, agent_participants


async def _require_addressable(
	session: AsyncSession,
	thread_id: TypeID,
	mention: MessageMentionSchema,
	principal: Principal,
) -> ThreadParticipant | None:
	"""reject a subject the caller cannot address in this thread."""
	match mention.type:
		case MentionableSubjectType.AGENT:
			await require_resource_access(
				mention.id,
				session,
				principal,
				ResourceType.AGENT,
				required_level=AccessLevel.READER,
			)
			participant = await get_thread_participant(
				session, thread_id, agent_id=mention.id
			)
			if participant is None:
				raise HTTPException(
					status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
					detail="agent is not a participant of this thread",
				)
			return participant
		case MentionableSubjectType.USER:
			addressable = await session.scalar(
				select(User.id).where(
					User.id == mention.id,
					user_addressable_predicate(principal),
				)
			)
			if addressable is None:
				raise HTTPException(
					status_code=status.HTTP_404_NOT_FOUND,
					detail="user not found",
				)
		case MentionableSubjectType.GROUP:
			await require_resource_access(
				mention.id,
				session,
				principal,
				ResourceType.GROUP,
				required_level=AccessLevel.READER,
			)
			if await session.get(Group, mention.id) is None:
				raise HTTPException(
					status_code=status.HTTP_404_NOT_FOUND,
					detail="group not found",
				)
	return None


async def resolve_invoked_agents(
	session: AsyncSession,
	mentions: list[MessageMentionSchema],
	agent_participants: dict[TypeID, ThreadParticipant],
) -> list[TypeID]:
	"""which addressed agents opted into answering when mentioned."""
	invoked: list[TypeID] = []
	seen: set[TypeID] = set()
	for mention in mentions:
		if mention.type != MentionableSubjectType.AGENT:
			continue
		if mention.id in seen:
			continue
		participant = agent_participants.get(mention.id)
		if participant is None:
			continue
		if participant.invoke_on_mention is not None:
			enabled = participant.invoke_on_mention
		else:
			agent = await session.get(Agent, mention.id)
			enabled = bool(
				agent and agent.parsed_config.features.invoke_on_mention.enabled
			)
		if enabled:
			seen.add(mention.id)
			invoked.append(mention.id)
	return invoked


async def message_mentions_agent(
	session: AsyncSession,
	thread_id: TypeID,
	message_id: TypeID,
	agent_id: TypeID,
) -> bool:
	"""whether a persisted message addresses a specific agent."""
	stmt = (
		select(MessageMention.id)
		.join(Message, Message.id == MessageMention.message_id)
		.where(
			Message.thread_id == thread_id,
			MessageMention.message_id == message_id,
			MessageMention.agent_id == agent_id,
		)
	)
	return await session.scalar(stmt) is not None
