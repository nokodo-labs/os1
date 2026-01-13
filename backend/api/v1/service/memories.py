"""service layer for memory operations."""

from __future__ import annotations

import os
import struct

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.memory import Memory
from api.schemas.memory import MemoryCreate, MemoryUpdate
from api.v1.service.auth import Principal
from api.v1.service.embeddings import resolve_embedding_model
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.vectorstores import add_chunks, delete_chunks
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.typeid import TypeID


def _embedding_to_bytes(embedding: list[float]) -> bytes:
	"""convert embedding list to bytes for storage."""
	return struct.pack(f"<{len(embedding)}f", *embedding)


def _get_default_embedding_model() -> EmbeddingModel:
	"""get a best-effort default embedding model for quick testing.

	this intentionally avoids settings/db wiring.
	"""
	api_key = os.environ.get("OPENAI_API_KEY")
	if not api_key:
		raise ValueError("OPENAI_API_KEY is required to embed memories")

	# hardcoded for quick iteration as requested
	return EmbeddingModel.model_validate(
		{
			"provider": "openai",
			"model_name": "text-embedding-3-large",
			"adapter": {
				"type": "openai.embedding",
				"api_key": api_key,
			},
		}
	)


def _memories_collection(*, user_id: TypeID) -> str:
	"""compute a stable per-user collection name for memories."""
	return f"memories-{user_id}"


async def _resolve_memories_embedding_model(
	session: AsyncSession,
	*,
	embedding_model_id: TypeID | None,
) -> EmbeddingModel:
	if embedding_model_id is None:
		return _get_default_embedding_model()
	return await resolve_embedding_model(session, embedding_model_id)


async def _get_memory(
	memory_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Memory:
	stmt = (
		select(Memory).options(selectinload(Memory.owner)).where(Memory.id == memory_id)
	)
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
	*,
	principal: Principal,
	embedding_model_id: TypeID | None = None,
) -> Memory:
	data = memory_in.model_dump(by_alias=True)
	if not principal.is_admin:
		data["user_id"] = principal.user.id
	memory = Memory(**data)
	session.add(memory)
	await session.commit()
	await session.refresh(memory)

	embedding_model = await _resolve_memories_embedding_model(
		session,
		embedding_model_id=embedding_model_id,
	)
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

	return await _get_memory(TypeID(memory.id), session, principal)


async def list_memories(
	session: AsyncSession,
	*,
	principal: Principal,
	user_id: TypeID,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Memory]:
	if not principal.is_admin:
		user_id = TypeID(principal.user.id)

	stmt = (
		apply_sort(
			select(Memory)
			.options(selectinload(Memory.owner))
			.where(Memory.user_id == user_id),
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns={
				"updated_at": Memory.updated_at,
				"created_at": Memory.created_at,
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
	*,
	principal: Principal,
) -> Memory:
	return await _get_memory(memory_id, session, principal)


async def update_memory(
	memory_id: TypeID,
	memory_in: MemoryUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
	embedding_model_id: TypeID | None = None,
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
		embedding_model = await _resolve_memories_embedding_model(
			session,
			embedding_model_id=embedding_model_id,
		)
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


async def delete_memory(
	memory_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	"""delete a memory and remove from vectorstore."""
	memory = await _get_memory(memory_id, session, principal)

	collection = _memories_collection(user_id=TypeID(memory.user_id))
	chunk = Chunk(id=str(memory.id), embedding=[])
	await delete_chunks(collection=collection, chunks=[chunk])

	await session.delete(memory)
	await session.commit()
