"""service layer for memory operations."""

from __future__ import annotations

import struct

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.memory import Memory
from api.schemas.memory import MemoryCreate, MemoryUpdate
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.embeddings import (
	build_embedding_model,
	resolve_embedding_model,
)
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.vectorstores import add_chunks, delete_chunks
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.utils.typeid import TypeID


def _embedding_to_bytes(embedding: list[float]) -> bytes:
	"""convert embedding list to bytes for storage."""
	return struct.pack(f"<{len(embedding)}f", *embedding)


def _memories_collection(*, user_id: TypeID) -> str:
	"""compute a stable per-user collection name for memories."""
	return f"memories-{user_id}"


async def _get_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Memory:
	stmt = select(Memory).where(Memory.id == memory_id)
	if not principal.is_admin:
		stmt = stmt.where(Memory.user_id == principal.user.id)
	result = await session.execute(stmt)
	memory = result.scalars().one_or_none()
	if not memory:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Memory not found",
		)
	return memory


async def create_memory(
	memory_in: MemoryCreate,
	session: AsyncSession,
	principal: Principal,
	*,
	origin_session_id: str | None = None,
) -> Memory:
	require_permission(principal, "memories:create")
	data = memory_in.model_dump(by_alias=True)
	if not principal.is_admin:
		data["user_id"] = principal.user.id
	memory = Memory(**data)
	session.add(memory)
	await session.flush()
	await session.refresh(memory)
	memory_id = TypeID(memory.id)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MEMORY_CREATED,
		data={"memory_id": str(memory_id)},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	embedding_model = build_embedding_model(await resolve_embedding_model(session))
	embeddings = await embedding_model.embed([memory.content])
	embedding = embeddings[0]

	collection = _memories_collection(user_id=TypeID(memory.user_id))
	chunk = Chunk(
		id=str(memory.id),
		content=memory.content,
		embedding=embedding,
		metadata={"user_id": str(memory.user_id)},
	)
	await add_chunks(collection=collection, chunks=[chunk])
	memory.embedding = _embedding_to_bytes(embedding)
	await session.commit()

	return await _get_memory(memory_id, session, principal)


async def list_memories(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
	search: str | None = None,
) -> list[Memory]:
	if not principal.is_admin:
		user_id = TypeID(principal.user.id)

	base = select(Memory).where(Memory.user_id == user_id)
	if search:
		base = base.where(Memory.content.ilike(f"%{search}%"))

	stmt = (
		apply_sort(
			base,
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns={
				"updated_at": Memory.updated_at,
				"created_at": Memory.created_at,
				"content_length": func.length(Memory.content),
				"category": Memory.category,
				"last_accessed_at": Memory.last_accessed_at,
				"confidence": Memory.confidence,
			},
			tie_breaker=Memory.id,
		)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Memory:
	return await _get_memory(memory_id, session, principal)


async def update_memory(
	memory_id: TypeID,
	memory_in: MemoryUpdate,
	session: AsyncSession,
	principal: Principal,
	*,
	origin_session_id: str | None = None,
) -> Memory:
	"""update a memory and sync with vectorstore if content changed."""
	memory = await _get_memory(memory_id, session, principal)

	content_changed = (
		memory_in.content is not None and memory_in.content != memory.content
	)
	if memory_in.content is not None:
		memory.content = memory_in.content
	if memory_in.confidence is not None:
		memory.confidence = memory_in.confidence
	if memory_in.category is not None:
		memory.category = memory_in.category

	if content_changed:
		embedding_model = build_embedding_model(await resolve_embedding_model(session))
		embeddings = await embedding_model.embed([memory.content])
		embedding = embeddings[0]

		collection = _memories_collection(user_id=TypeID(memory.user_id))
		chunk = Chunk(
			id=str(memory.id),
			content=memory.content,
			embedding=embedding,
			metadata={"user_id": str(memory.user_id)},
		)
		await add_chunks(collection=collection, chunks=[chunk])
		memory.embedding = _embedding_to_bytes(embedding)

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MEMORY_UPDATED,
		data={"memory_id": str(memory_id)},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return await _get_memory(memory_id, session, principal)


async def delete_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	origin_session_id: str | None = None,
) -> None:
	"""delete a memory and remove from vectorstore."""
	memory = await _get_memory(memory_id, session, principal)

	collection = _memories_collection(user_id=TypeID(memory.user_id))
	chunk = Chunk(id=str(memory.id), embedding=[])
	await delete_chunks(collection=collection, chunks=[chunk])

	await session.delete(memory)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MEMORY_DELETED,
		data={"memory_id": str(memory_id)},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)


async def delete_all_memories(
	session: AsyncSession,
	principal: Principal,
	*,
	origin_session_id: str | None = None,
) -> None:
	"""delete all memories for the current user and wipe vectorstore."""
	user_id = TypeID(principal.user.id)

	id_result = await session.execute(
		select(Memory.id).where(Memory.user_id == user_id)
	)
	memory_ids = list(id_result.scalars().all())

	if len(memory_ids) > 0:
		collection = _memories_collection(user_id=user_id)
		chunks = [Chunk(id=str(mid), embedding=[]) for mid in memory_ids]
		await delete_chunks(collection=collection, chunks=chunks)

		await session.execute(delete(Memory).where(Memory.user_id == user_id))
		event = Event(
			scope=EventScope.USER,
			scope_id=principal.user_id,
			type=EventType.MEMORY_DELETED,
			data={"all": True, "user_id": str(user_id)},
			user_id=principal.user_id,
		)
		await event_service.publish_event(
			session,
			event=event,
			origin_session_id=origin_session_id,
		)
