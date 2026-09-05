"""internal derivative files derived from a parent user file.

a derivative is a real File row whose source is an internal kind (text
extraction, thumbnail, ...), linked to its parent by parent_file_id and owned by
no user so access rules alone gate it. each (parent, source) pair holds at most
one derivative as an app-level rule; these helpers enforce it by reusing the
existing row in place.
"""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File, FileSource, FileStatus
from api.settings import settings
from api.storage import get_storage_backend, new_storage_key
from api.storage.base import MimeType
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)


async def find_derived_file(
	parent_file_id: TypeID,
	source: FileSource,
	session: AsyncSession,
) -> File | None:
	"""load a parent's derivative of the given source, if any."""
	result = await session.execute(
		select(File).where(
			File.parent_file_id == str(parent_file_id),
			File.source == source,
			File.deleted_at.is_(None),
		)
	)
	return result.scalars().one_or_none()


async def has_derived_file(
	parent_file_id: TypeID,
	source: FileSource,
	session: AsyncSession,
) -> bool:
	"""return whether a parent already has a derivative of the given source."""
	result = await session.execute(
		select(File.id)
		.where(
			File.parent_file_id == str(parent_file_id),
			File.source == source,
			File.deleted_at.is_(None),
		)
		.limit(1)
	)
	return result.scalar_one_or_none() is not None


async def write_derived_file(
	parent: File,
	source: FileSource,
	data: bytes,
	mime_type: MimeType,
	key_prefix: str,
	session: AsyncSession,
) -> File:
	"""write bytes as a parent's derivative of the given source.

	reuses the existing derivative row when present, repointing it at a fresh
	blob and dropping the old one, since bytes are immutable.
	"""
	checksum = hashlib.sha256(data).hexdigest()
	backend_name = settings.assets.storage.active_backend
	backend = get_storage_backend(backend_name)
	key = new_storage_key(prefix=key_prefix)
	await backend.put(key, data, mime_type)
	child = await find_derived_file(parent.id, source, session)
	if child is None:
		child = File(
			id=TypeID(new_typeid("file")),
			owner_id=None,
			source=source,
			storage_backend=backend_name,
			storage_key=key,
			filename=parent.filename,
			mime_type=mime_type,
			size_bytes=len(data),
			checksum_sha256=checksum,
			status=FileStatus.AVAILABLE,
			parent_file_id=str(parent.id),
		)
		session.add(child)
		await session.flush()
		return child
	old_backend, old_key = child.storage_backend, child.storage_key
	child.storage_backend = backend_name
	child.storage_key = key
	child.mime_type = mime_type
	child.size_bytes = len(data)
	child.checksum_sha256 = checksum
	await session.flush()
	await _delete_blob(old_backend, old_key)
	return child


async def read_derived_file_bytes(
	parent_file_id: TypeID,
	source: FileSource,
	session: AsyncSession,
) -> bytes | None:
	"""read a parent's derivative bytes, or None when there is none."""
	child = await find_derived_file(parent_file_id, source, session)
	if child is None:
		return None
	backend = get_storage_backend(child.storage_backend)
	if not await backend.exists(child.storage_key):
		logger.warning(
			"derived-file blob missing parent=%s source=%s child=%s",
			parent_file_id,
			source.value,
			child.id,
		)
		return None
	stream = await backend.get(child.storage_key)
	return b"".join([part async for part in stream])


async def delete_derived_file(
	parent_file_id: TypeID,
	source: FileSource,
	session: AsyncSession,
) -> None:
	"""delete a parent's derivative of the given source and its bytes, if any."""
	child = await find_derived_file(parent_file_id, source, session)
	if child is None:
		return
	await _delete_blob(child.storage_backend, child.storage_key)
	await session.delete(child)
	await session.flush()


async def delete_all_derived_file_bytes(
	parent_file_id: TypeID,
	session: AsyncSession,
) -> None:
	"""delete every derivative's stored bytes for a parent (any source).

	the parent's FK cascade drops the derivative rows; this drops their storage
	objects, which the cascade cannot reach.
	"""
	result = await session.execute(
		select(File).where(File.parent_file_id == str(parent_file_id))
	)
	for child in result.scalars().all():
		await _delete_blob(child.storage_backend, child.storage_key)


async def _delete_blob(backend_name: str, key: str) -> None:
	"""best-effort removal of a stored object."""
	try:
		await get_storage_backend(backend_name).delete(key)
	except Exception:
		logger.warning("failed to delete derived-file blob %s", key, exc_info=True)
