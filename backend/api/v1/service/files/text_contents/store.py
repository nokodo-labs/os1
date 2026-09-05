"""stored text content: persist, retrieve, and line-range reads.

the extracted body text is kept as a derived file (one per parent, owned by no
user). this module owns writing, reading, and deleting that artifact, plus
direct line-range reads of it. char offsets match the chunker's because the
text is stored normalized.
"""

import logging
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.file import File, FileSource
from api.permissions import ResourceType
from api.v1.service.authentication import Principal
from api.v1.service.authorization import require_resource_access
from api.v1.service.files.derived_files import (
	delete_derived_file,
	has_derived_file,
	read_derived_file_bytes,
	write_derived_file,
)
from nokodo_ai.chunkers import normalize_text
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

EXTRACTED_TEXT_KEY_PREFIX = "extracted"
EXTRACTED_TEXT_MIME = "text/plain; charset=utf-8"


@dataclass(slots=True)
class FileContentLines:
	"""a slice of a file's extracted text addressed by line range."""

	text: str
	line_start: int
	line_end: int
	total_lines: int


async def store_extracted_text(
	file: File,
	raw_text: str,
	session: AsyncSession,
) -> None:
	"""persist a file's normalized extracted body text as a derived file.

	a derived file is always written, even for empty text: its existence is the
	marker that extraction has run. idempotent.
	"""
	await write_derived_file(
		file,
		FileSource.TEXT_EXTRACTION,
		normalize_text(raw_text).encode("utf-8"),
		EXTRACTED_TEXT_MIME,
		EXTRACTED_TEXT_KEY_PREFIX,
		session,
	)


async def has_extracted_text_child(
	parent_file_id: TypeID,
	session: AsyncSession,
) -> bool:
	"""return whether a file already has its extracted-text derived file."""
	return await has_derived_file(parent_file_id, FileSource.TEXT_EXTRACTION, session)


async def read_extracted_text(file: File, session: AsyncSession) -> str | None:
	"""read a file's extracted text from its derived file, or None."""
	data = await read_derived_file_bytes(file.id, FileSource.TEXT_EXTRACTION, session)
	return data.decode("utf-8") if data is not None else None


async def delete_extracted_text(file: File, session: AsyncSession) -> None:
	"""delete a file's derived extracted-text file and its bytes, if any."""
	await delete_derived_file(file.id, FileSource.TEXT_EXTRACTION, session)


async def read_file_content_lines(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	line_start: int | None = None,
	line_end: int | None = None,
) -> FileContentLines:
	"""read a line range of a file's extracted text. requires read access.

	lines are 1-based and inclusive. a missing or non-positive line_start
	starts at line 1; a missing or non-positive line_end runs to the end.
	bounds are clamped to the available range.
	"""
	file = await load_accessible_file(file_id, session, principal)
	full_text = await read_extracted_text(file, session)
	return _slice_lines(full_text, line_start, line_end)


def _slice_lines(
	full_text: str | None,
	line_start: int | None,
	line_end: int | None,
) -> FileContentLines:
	"""clamp a 1-based inclusive line range and return the selected text."""
	if not full_text:
		return FileContentLines(text="", line_start=0, line_end=0, total_lines=0)
	lines = full_text.split("\n")
	total = len(lines)
	start = line_start if line_start and line_start > 0 else 1
	end = line_end if line_end and line_end > 0 else total
	start = max(1, start)
	end = min(total, end)
	if start > end:
		return FileContentLines(
			text="", line_start=start, line_end=end, total_lines=total
		)
	return FileContentLines(
		text="\n".join(lines[start - 1 : end]),
		line_start=start,
		line_end=end,
		total_lines=total,
	)


async def load_accessible_file(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> File:
	"""load a non-deleted file after enforcing reader access."""
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.READER,
	)
	result = await session.execute(
		select(File).where(File.id == file_id, File.deleted_at.is_(None))
	)
	file = result.scalars().one_or_none()
	if file is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file
