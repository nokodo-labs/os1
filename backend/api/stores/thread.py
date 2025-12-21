"""sqlalchemy-backed thread store implementing sdk ThreadStore protocol."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message as MessageORM
from api.models.thread import Thread as ThreadORM
from api.stores.message import _message_to_orm, _validate_message
from api.typeid import TypeID
from nokodo_ai.models import (
	ConflictError,
	Message,
	NotFoundError,
	Thread,
)


def _validate_thread(orm: ThreadORM) -> Thread:
	data: dict[str, object] = {
		"id": orm.id,
		"owner_id": orm.owner_id,
		"title": orm.title,
		"tags": orm.tags,
		"is_archived": orm.is_archived,
		"spawned_from_message_id": orm.spawned_from_message_id,
		"current_message_id": orm.current_message_id,
		"last_activity_at": orm.last_activity_at,
		"metadata": dict(orm.metadata_),
		"created_at": orm.created_at,
		"updated_at": orm.updated_at,
	}
	return Thread.model_validate(data)


def _thread_kwargs(thread: Thread) -> dict[str, Any]:
	return {
		"id": TypeID(thread.id),
		"owner_id": TypeID(thread.owner_id),
		"title": thread.title,
		"tags": list(thread.tags),
		"is_archived": thread.is_archived,
		"spawned_from_message_id": TypeID(thread.spawned_from_message_id)
		if thread.spawned_from_message_id
		else None,
		"current_message_id": TypeID(thread.current_message_id)
		if thread.current_message_id
		else None,
		"metadata_": dict(thread.metadata),
	}


class ThreadStore:
	"""sqlalchemy thread store implementing sdk ThreadStore protocol."""

	def __init__(self, session: AsyncSession) -> None:
		self._session = session

	async def get(self, thread_id: str) -> Thread | None:
		orm = await self._session.get(ThreadORM, thread_id)
		if orm is None:
			return None
		return _validate_thread(orm)

	async def save(self, thread: Thread) -> Thread:
		existing = await self._session.get(ThreadORM, thread.id)
		if existing is None:
			kwargs = _thread_kwargs(thread)
			if thread.last_activity_at is not None:
				kwargs["last_activity_at"] = thread.last_activity_at

			orm = ThreadORM(**kwargs)
			self._session.add(orm)
			await self._session.flush()
			await self._session.refresh(orm)
			return _validate_thread(orm)

		existing.owner_id = TypeID(thread.owner_id)
		existing.title = thread.title
		existing.tags = list(thread.tags)
		existing.is_archived = thread.is_archived
		existing.spawned_from_message_id = (
			TypeID(thread.spawned_from_message_id)
			if thread.spawned_from_message_id
			else None
		)
		existing.current_message_id = (
			TypeID(thread.current_message_id) if thread.current_message_id else None
		)
		if thread.last_activity_at is not None:
			existing.last_activity_at = thread.last_activity_at
		existing.metadata_ = dict(thread.metadata)

		await self._session.flush()
		await self._session.refresh(existing)
		return _validate_thread(existing)

	async def delete(self, thread_id: str) -> None:
		orm = await self._session.get(ThreadORM, thread_id)
		if orm is None:
			return
		orm.soft_delete()
		await self._session.flush()

	async def set_current_message(
		self, thread_id: str, message_id: str | None
	) -> Thread:
		orm = await self._session.get(ThreadORM, thread_id)
		if orm is None:
			raise NotFoundError("thread", thread_id)

		if message_id is None:
			orm.current_message_id = None
			await self._session.flush()
			await self._session.refresh(orm)
			return _validate_thread(orm)

		message = await self._session.get(MessageORM, message_id)
		if message is None or str(message.thread_id) != thread_id:
			raise NotFoundError("message", message_id)

		orm.current_message_id = TypeID(message_id)
		await self._session.flush()
		await self._session.refresh(orm)
		return _validate_thread(orm)

	async def append_message(self, message: Message) -> Message:
		if message.thread_id == "":
			raise ConflictError("message.thread_id is required")

		thread = await self._session.get(ThreadORM, message.thread_id)
		if thread is None:
			raise NotFoundError("thread", message.thread_id)

		existing = await self._session.get(MessageORM, message.id)
		if existing is not None:
			raise ConflictError("message already exists")

		parent_id = message.parent_id
		if parent_id is None:
			parent_id = (
				str(thread.current_message_id) if thread.current_message_id else None
			)
		else:
			parent = await self._session.get(MessageORM, parent_id)
			if parent is None or str(parent.thread_id) != message.thread_id:
				raise NotFoundError("parent_message", parent_id)

		message_with_parent = message.model_copy(update={"parent_id": parent_id})
		orm = _message_to_orm(message_with_parent)
		self._session.add(orm)
		await self._session.flush()

		thread.last_activity_at = datetime.now(tz=UTC)
		thread.current_message_id = orm.id
		await self._session.flush()
		await self._session.refresh(orm)
		return _validate_message(orm)
