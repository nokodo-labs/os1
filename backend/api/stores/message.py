"""sqlalchemy-backed message store implementing sdk MessageStore protocol."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import AssistantMessage as AssistantMessageORM
from api.models.message import Message as MessageORM
from api.models.message import MessageType as MessageTypeORM
from api.models.message import SystemMessage as SystemMessageORM
from api.models.message import ToolMessage as ToolMessageORM
from api.models.message import UserMessage as UserMessageORM
from api.typeid import TypeID
from nokodo_ai.models import (
	ConflictError,
	Message,
	MessageType,
)


_MessageAdapter = TypeAdapter(Annotated[Message, Field(discriminator="type")])


def _validate_message(orm: MessageORM) -> Message:
	data: dict[str, object] = {
		"id": orm.id,
		"thread_id": orm.thread_id,
		"parent_id": orm.parent_id,
		"task_id": orm.task_id,
		"sender_agent_id": orm.sender_agent_id,
		"sender_user_id": orm.sender_user_id,
		"type": orm.type.value,
		"content": orm.content,
		"attachments": orm.attachments,
		"tool_calls": orm.tool_calls,
		"token_usage": orm.token_usage,
		"read_by": orm.read_by,
		"metadata": dict(orm.metadata_),
		"created_at": orm.created_at,
		"updated_at": orm.updated_at,
	}
	return _MessageAdapter.validate_python(data)


def _message_to_orm(message: Message) -> MessageORM:
	"""convert SDK domain model to ORM for insert."""
	orm_type = MessageTypeORM(message.type.value)
	kwargs: dict[str, Any] = {
		"id": TypeID(message.id),
		"thread_id": TypeID(message.thread_id),
		"parent_id": TypeID(message.parent_id) if message.parent_id else None,
		"task_id": TypeID(message.task_id) if message.task_id else None,
		"sender_agent_id": TypeID(message.sender_agent_id)
		if message.sender_agent_id
		else None,
		"sender_user_id": TypeID(message.sender_user_id)
		if message.sender_user_id
		else None,
		"content": message.content,
		"attachments": list(message.attachments),
		"tool_calls": list(message.tool_calls),
		"token_usage": dict(message.token_usage) if message.token_usage else None,
		"read_by": list(message.read_by),
		"metadata_": dict(message.metadata),
		"type": orm_type,
	}

	mapping = {
		MessageTypeORM.USER: UserMessageORM,
		MessageTypeORM.ASSISTANT: AssistantMessageORM,
		MessageTypeORM.TOOL: ToolMessageORM,
		MessageTypeORM.SYSTEM: SystemMessageORM,
	}
	return mapping[orm_type](**kwargs)


class MessageStore:
	"""sqlalchemy message store implementing sdk MessageStore protocol."""

	def __init__(self, session: AsyncSession) -> None:
		self._session = session

	async def get(self, message_id: str) -> Message | None:
		orm = await self._session.get(MessageORM, message_id)
		if orm is None:
			return None
		return _validate_message(orm)

	async def save(self, message: Message) -> Message:
		existing = await self._session.get(MessageORM, message.id)
		if existing is None:
			orm = _message_to_orm(message)
			self._session.add(orm)
			await self._session.flush()
			await self._session.refresh(orm)
			return _validate_message(orm)

		if str(existing.thread_id) != message.thread_id:
			raise ConflictError("message thread_id cannot be changed")
		if MessageType(existing.type.value) != message.type:
			raise ConflictError("message type cannot be changed")

		existing.parent_id = TypeID(message.parent_id) if message.parent_id else None
		existing.task_id = TypeID(message.task_id) if message.task_id else None
		existing.sender_agent_id = (
			TypeID(message.sender_agent_id) if message.sender_agent_id else None
		)
		existing.sender_user_id = (
			TypeID(message.sender_user_id) if message.sender_user_id else None
		)
		existing.content = message.content
		existing.attachments = list(message.attachments)
		existing.tool_calls = list(message.tool_calls)
		existing.token_usage = (
			dict(message.token_usage) if message.token_usage else None
		)
		existing.read_by = list(message.read_by)
		existing.metadata_ = dict(message.metadata)

		await self._session.flush()
		await self._session.refresh(existing)
		return _validate_message(existing)

	async def delete(self, message_id: str) -> None:
		orm = await self._session.get(MessageORM, message_id)
		if orm is None:
			return
		await self._session.delete(orm)
		await self._session.flush()

	async def list_by_thread(
		self,
		thread_id: str,
		*,
		limit: int = 100,
		offset: int = 0,
	) -> list[Message]:
		stmt = (
			select(MessageORM)
			.where(MessageORM.thread_id == thread_id)
			.order_by(MessageORM.created_at)
			.offset(offset)
			.limit(limit)
		)
		result = await self._session.execute(stmt)
		return [_validate_message(orm) for orm in result.scalars().all()]

	async def list_by_parent(
		self,
		*,
		thread_id: str,
		parent_id: str | None,
		limit: int = 100,
		offset: int = 0,
	) -> list[Message]:
		stmt = (
			select(MessageORM)
			.where(MessageORM.thread_id == thread_id, MessageORM.parent_id == parent_id)
			.order_by(MessageORM.created_at)
			.offset(offset)
			.limit(limit)
		)
		result = await self._session.execute(stmt)
		return [_validate_message(orm) for orm in result.scalars().all()]
