"""file description and summary pipeline."""

from __future__ import annotations

import logging

from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File
from api.settings import settings
from api.v1.service.chat.models import resolve_task_chat_model
from api.v1.service.files.content_vectorization import (
	FileContentChunk,
	load_file_content_chunks,
)
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """write concise file metadata for nokodo AI.

for text-adjacent files, summarize the contents.
for non-text files, describe the likely contents from the available metadata.
return only the description text, with no heading."""


async def update_file_description(
	file: File,
	session: AsyncSession,
	content_chunks: list[FileContentChunk] | None = None,
	preserve_timestamps: bool = False,
) -> str | None:
	"""generate and persist the file description field.

	when preserve_timestamps=True the update is written via a targeted SQL
	statement that touches only the description column, leaving updated_at
	unchanged. use this for background backfill sweeps that should not surface
	as a user-visible edit. the default (False) goes through the ORM and bumps
	updated_at as usual.
	"""
	chunks = content_chunks
	if chunks is None:
		batch = await load_file_content_chunks(file, session)
		chunks = batch.chunks
	description = await build_file_description(file, chunks, session)
	if description is None:
		return file.description
	if preserve_timestamps:
		# bypass ORM to avoid triggering the onupdate for updated_at
		await session.execute(
			sql_update(File)
			.where(File.id == file.id)
			.values(description=description)
			.execution_options(synchronize_session="evaluate")
		)
	else:
		file.description = description
		await session.flush()
	return description


async def build_file_description(
	file: File,
	content_chunks: list[FileContentChunk],
	session: AsyncSession | None = None,
) -> str | None:
	"""build a summary/description using a task model when configured."""
	fallback = _fallback_description(file, content_chunks)
	try:
		chat_model = await resolve_task_chat_model(session, "asset_description")
		thread = SDKThread(
			messages=[
				SDKSystemMessage.from_text(_SYSTEM_PROMPT),
				SDKUserMessage.from_text(_description_prompt(file, content_chunks)),
			]
		)
		assistant = await chat_model.generate(thread, stream=False)
		description = (assistant.text or "").strip()
		if description:
			return _truncate_description(description)
	except Exception:
		logger.exception("file description generation failed for file %s", file.id)
	return fallback


def _description_prompt(file: File, content_chunks: list[FileContentChunk]) -> str:
	"""build the user prompt for file description generation."""
	metadata = [
		f"filename: {file.filename or 'file'}",
		f"mime type: {file.mime_type or 'unknown'}",
		f"size bytes: {file.size_bytes if file.size_bytes is not None else 'unknown'}",
	]
	if content_chunks:
		excerpt = _content_excerpt(content_chunks)
		metadata.append("contents excerpt:\n" + excerpt)
	else:
		metadata.append("contents excerpt: unavailable")
	return "\n".join(metadata)


def _content_excerpt(content_chunks: list[FileContentChunk]) -> str:
	"""join content chunks into the capped description-model excerpt."""
	max_chars = settings.assets.descriptions.max_input_chars
	parts: list[str] = []
	total = 0
	for chunk in content_chunks:
		if max_chars is None:
			parts.append(chunk.text)
			continue
		if total >= max_chars:
			break
		remaining = max_chars - total
		text = chunk.text[:remaining]
		parts.append(text)
		total += len(text)
	return "\n\n".join(parts).strip()


def _fallback_description(
	file: File,
	content_chunks: list[FileContentChunk],
) -> str | None:
	"""build a deterministic description when model generation is unavailable."""
	if content_chunks:
		first = _content_excerpt(content_chunks)
		if first:
			return _truncate_description(first.replace("\n", " "))
	parts = [file.filename or "file"]
	if file.mime_type:
		parts.append(file.mime_type)
	if file.size_bytes is not None:
		parts.append(f"{file.size_bytes} bytes")
	return _truncate_description(" - ".join(parts))


def _truncate_description(description: str) -> str:
	"""normalize and cap a stored file description."""
	limit = settings.assets.descriptions.max_chars
	clean = " ".join(description.split())
	if limit is None:
		return clean
	if len(clean) <= limit:
		return clean
	return clean[:limit].rstrip()
