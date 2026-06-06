"""Open WebUI memory import writers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.main import async_session_local, safe_rollback
from api.models.memory import Memory
from api.settings import OpenWebUIDeployment
from api.v1.service.integrations.open_webui.common import (
	ImportSummary,
	_epoch_to_dt,
	_first_str,
	_merge_metadata,
	_owui_field_filter,
	_owui_metadata,
	_owui_origin_filter,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def _find_memory_for_owui_id(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	owui_memory_id: str,
) -> Memory | None:
	result = await session.scalars(
		select(Memory)
		.where(
			Memory.user_id == owner_id,
			Memory.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Memory.metadata_, deployment),
			_owui_field_filter(Memory.metadata_, "memory_id", owui_memory_id),
		)
		.limit(1)
	)
	return result.one_or_none()


async def _import_memories(
	memories: Iterable[dict[str, Any]],
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> None:
	for raw in memories:
		content = raw.get("content")
		if not isinstance(content, str) or not content.strip():
			summary.memories_skipped += 1
			continue
		memory_id = _first_str(raw, "id", "memory_id")
		if memory_id is None:
			summary.memories_skipped += 1
			summary.add_error("memory skipped: missing Open WebUI id")
			continue
		metadata = _owui_metadata(
			deployment,
			"memory",
			memory_id,
			memory_id=memory_id,
		)
		existing = await _find_memory_for_owui_id(
			session=session,
			owner_id=owner_id,
			deployment=deployment,
			owui_memory_id=memory_id,
		)
		created_at = _epoch_to_dt(raw.get("created_at"))
		updated_at = _epoch_to_dt(raw.get("updated_at"))
		if existing is not None:
			existing.content = content
			existing.metadata_ = _merge_metadata(existing.metadata_, metadata)
			if created_at:
				existing.created_at = created_at
			if updated_at:
				existing.updated_at = updated_at
			summary.memories_skipped += 1
			continue
		memory = Memory(
			user_id=owner_id,
			content=content,
			metadata_=metadata,
		)
		session.add(memory)
		await session.flush()
		if created_at:
			memory.created_at = created_at
		if updated_at:
			memory.updated_at = updated_at
		summary.memory_ids.append(memory.id)
		summary.memories_imported += 1


async def _import_memories_chunk(
	memories: list[dict[str, Any]],
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	deployment_origin: str,
) -> ImportSummary:
	"""import a slice of memories in a dedicated session and commit it."""
	local = ImportSummary(deployment_origin=deployment_origin)
	async with async_session_local() as session:
		try:
			await _import_memories(
				memories,
				session=session,
				owner_id=owner_id,
				deployment=deployment,
				summary=local,
			)
			await session.commit()
		except Exception as exc:
			await safe_rollback(session)
			logger.exception("failed to import Open WebUI memories")
			local.add_error(f"memories import failed: {type(exc).__name__}")
	return local
