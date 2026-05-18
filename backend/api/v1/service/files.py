"""service layer for file operations.

provides both low-level storage primitives (store_file, read_content,
delete_content) and authenticated HTTP-facing operations (upload_file,
get_file_content, etc.).

low-level functions accept owner_id directly and skip access checks,
making them suitable for agents, tools, background jobs, and any
programmatic flow that doesn't originate from an HTTP request.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from collections.abc import AsyncIterator

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import case, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import ColumnElement, Select

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.file import File, FileSource, FileStatus
from api.models.many_to_many import file_project_association
from api.models.project import Project
from api.permissions import ResourceType
from api.schemas.file import File as FileOut
from api.schemas.file import (
	FileCategoryFilter,
	FileCounts,
	FileCreate,
	FileListFilters,
	FileUpdate,
)
from api.settings import settings
from api.storage import get_storage_backend
from api.storage.base import MimeType
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_resource,
	list_accessible_user_ids,
	require_permission,
	require_project_access,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.projects import invalidate_project_payload_caches, load_projects
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from nokodo_ai.utils.typeid import TypeID, new_typeid


log = logging.getLogger(__name__)

# internal helpers


async def _get_file(file_id: TypeID, session: AsyncSession) -> File:
	"""fetch a file record by id (no access check)."""
	result = await session.execute(
		select(File).where(File.id == file_id, File.deleted_at.is_(None))
	)
	file = result.scalars().one_or_none()
	if not file:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file


async def _get_file_with_projects(file_id: TypeID, session: AsyncSession) -> File:
	"""fetch a file record with project links by id (no access check)."""
	result = await session.execute(
		select(File)
		.where(File.id == file_id, File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	file = result.scalars().one_or_none()
	if not file:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file


def _uuid7_hex() -> str:
	"""generate a uuid v7 value as a 32-char lowercase hex string.

	rfc 9562 layout (128 bits):
	- bits 0-47:  unix timestamp in ms (big-endian)
	- bits 48-51: version nibble = 0b0111
	- bits 52-63: rand_a (12 random bits)
	- bits 64-65: variant = 0b10
	- bits 66-127: rand_b (62 random bits)

	time-ordered and globally unique.
	when python 3.14 is the minimum, swap this for uuid.uuid7().hex.
	"""
	ms = int(time.time() * 1000) & 0xFFFF_FFFF_FFFF  # 48 bits
	rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
	rand_a = (rand >> 68) & 0x0FFF  # top 12
	rand_b = rand & 0x3FFF_FFFF_FFFF_FFFF  # bottom 62
	hi = (ms << 16) | (0x7 << 12) | rand_a
	lo = (0b10 << 62) | rand_b
	return f"{hi:016x}{lo:016x}"


def _new_storage_key(prefix: str | None = None) -> str:
	"""generate a fresh opaque storage key for each stored object.

	uses uuid v7 (rfc 9562, python 3.13 stdlib): time-ordered, globally
	unique, 32 compact hex chars. fully independent from the file's db id,
	so ownership changes and re-keys never require moving bytes.

	an optional prefix enables s3 lifecycle rules (e.g. 'tmp/' for
	auto-expiry) without embedding ownership semantics into the path.
	"""
	key = _uuid7_hex()
	if prefix:
		return f"{prefix.rstrip('/')}/{key}"
	return key


async def _stream_upload(upload: UploadFile) -> AsyncIterator[bytes]:
	"""yield chunks from an UploadFile without loading entire file into memory."""
	while chunk := await upload.read(256 * 1024):
		yield chunk


async def _emit_file_event(
	session: AsyncSession,
	event_type: EventType,
	file_id: TypeID,
	user_id: TypeID,
	filename: str | None = None,
	origin_session_id: str | None = None,
	recipient_ids: list[TypeID] | None = None,
) -> None:
	"""persist and fanout a file lifecycle event."""
	data: dict[str, str | None] = {"id": str(file_id)}
	if filename is not None:
		data["filename"] = filename
	event = Event(
		scope=EventScope.USER,
		scope_id=user_id,
		type=event_type,
		data=data,
		user_id=user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
		recipient_ids=recipient_ids,
	)


# ---------------------------------------------------------------------------
# low-level storage primitives (no auth, no HTTP deps)
# ---------------------------------------------------------------------------


async def store_file(
	session: AsyncSession,
	data: bytes | AsyncIterator[bytes],
	owner_id: TypeID,
	filename: str | None = None,
	content_type: MimeType = "application/octet-stream",
	source: FileSource = FileSource.GENERATED,
	project_ids: list[TypeID] | None = None,
	message_id: TypeID | None = None,
	backend_name: str | None = None,
	key_prefix: str | None = None,
	create_event: bool = True,
	origin_session_id: str | None = None,
) -> File:
	"""store bytes and create a File record.

	this is the generic entry point for programmatic file creation.
	agents, tools, background jobs, and imports should use this
	instead of the HTTP-facing upload_file().

	does NOT check access permissions - the caller is responsible
	for authorization in their own context.
	"""
	if backend_name is None:
		backend_name = settings.assets.storage.backend
	backend = get_storage_backend(backend_name)

	file_id = new_typeid("file")
	key = _new_storage_key(prefix=key_prefix)

	await backend.put(key, data, content_type)

	if isinstance(data, (bytes, bytearray, memoryview)):
		size_bytes: int | None = len(data)
		checksum: str | None = hashlib.sha256(data).hexdigest()
	else:
		info = await backend.stat(key)
		size_bytes = info.size if info else None
		checksum = await backend.checksum_sha256(key)

	projects: list[Project] = []
	if project_ids:
		result = await session.scalars(
			select(Project).where(Project.id.in_(project_ids))
		)
		projects = list(result.all())

	file = File(
		id=file_id,
		owner_id=owner_id,
		source=source,
		storage_backend=backend_name,
		storage_key=key,
		filename=filename,
		mime_type=content_type,
		size_bytes=size_bytes,
		checksum_sha256=checksum,
		status=FileStatus.AVAILABLE,
		message_id=message_id,
		projects=projects,
	)
	session.add(file)
	await session.flush()

	if create_event:
		await _emit_file_event(
			session,
			event_type=EventType.FILE_CREATED,
			file_id=file_id,
			user_id=owner_id,
			filename=filename,
			origin_session_id=origin_session_id,
		)
	await invalidate_project_payload_caches(set(project_ids or []))

	return file


async def read_content(
	file: File,
) -> tuple[AsyncIterator[bytes], MimeType | None, int | None]:
	"""read file content from storage (no access check).

	returns (stream, content_type, size_bytes).
	raises FileNotFoundError when the object is missing from storage.
	"""
	backend = get_storage_backend(file.storage_backend)
	if not await backend.exists(file.storage_key):
		raise FileNotFoundError(
			f"storage object missing: {file.storage_key!r} "
			f"on backend {file.storage_backend!r}"
		)
	stream = await backend.get(file.storage_key)
	return stream, file.mime_type, file.size_bytes


async def resolve_file_data(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> str | None:
	"""resolve a file record to base64-encoded data (access-checked).

	always reads bytes through the storage backend and encodes as base64.
	this keeps the backend as the single auth gatekeeper - the storage
	layer is never exposed directly, regardless of which backend is active.

	the caller must supply a principal so file ownership / ACL is enforced.

	returns base64 string on success, or None when the file or storage
	object is missing, or the principal lacks access.
	"""
	result = await session.execute(
		select(File).where(File.id == file_id, File.deleted_at.is_(None))
	)
	file = result.scalars().one_or_none()
	if file is None:
		log.warning("resolve_file_data: file %s not found", file_id)
		return None

	# enforce access - silently return None when denied so the caller
	# treats it identically to "file not found" (no info leak).
	try:
		await require_resource_access(
			file_id,
			session,
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		)
	except HTTPException:
		log.warning(
			"resolve_file_data: access denied for file %s (user %s)",
			file_id,
			principal.user_id,
		)
		return None

	try:
		stream, _, _ = await read_content(file)
	except FileNotFoundError:
		log.warning(
			"resolve_file_data: storage object missing for file %s",
			file.id,
		)
		return None

	chunks: list[bytes] = []
	async for chunk in stream:
		chunks.append(chunk)
	raw = b"".join(chunks)
	return base64.standard_b64encode(raw).decode("ascii")


async def delete_content(file: File) -> None:
	"""delete file bytes from storage (no access check).

	silently logs failures instead of raising, since orphaned storage
	objects are less harmful than a loud crash during cleanup.
	"""
	try:
		backend = get_storage_backend(file.storage_backend)
		await backend.delete(file.storage_key)
	except Exception:
		log.warning(
			"failed to delete storage object %s from %s",
			file.storage_key,
			file.storage_backend,
			exc_info=True,
		)


# ---------------------------------------------------------------------------
# authenticated operations (HTTP-facing, access-checked)
# ---------------------------------------------------------------------------


async def create_file(
	file_in: FileCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> File:
	"""register a new file record (metadata only, no bytes)."""
	require_permission(principal, "files:create")
	for pid in file_in.project_ids:
		await require_project_access(
			pid,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	data = file_in.model_dump(by_alias=True, exclude={"project_ids"})
	data["owner_id"] = principal.user_id
	projects = (
		await load_projects(file_in.project_ids, session, principal)
		if file_in.project_ids
		else []
	)
	file = File(**data, projects=projects)
	session.add(file)
	await session.flush()

	await _emit_file_event(
		session,
		event_type=EventType.FILE_CREATED,
		file_id=file.id,
		user_id=principal.user_id,
		filename=file.filename,
		origin_session_id=origin_session_id,
	)
	await invalidate_project_payload_caches(set(file_in.project_ids))
	return file


async def upload_file(
	upload: UploadFile,
	session: AsyncSession,
	principal: Principal,
	project_ids: list[TypeID] | None = None,
	source: FileSource = FileSource.UPLOAD,
	origin_session_id: str | None = None,
) -> File:
	"""upload a file via HTTP multipart and create the record.

	delegates to store_file() after extracting data from the UploadFile
	and checking permissions.
	"""
	require_permission(principal, "files:create")
	for pid in project_ids or []:
		await require_project_access(
			pid,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)

	content_type: MimeType = upload.content_type or "application/octet-stream"

	# small files: read fully into memory; large/unknown: stream
	if upload.size is not None and upload.size < 10 * 1024 * 1024:
		file_data: bytes | AsyncIterator[bytes] = await upload.read()
	else:
		file_data = _stream_upload(upload)

	return await store_file(
		session,
		data=file_data,
		owner_id=principal.user_id,
		filename=upload.filename,
		content_type=content_type,
		source=source,
		project_ids=project_ids,
		origin_session_id=origin_session_id,
	)


async def get_file_content(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> tuple[AsyncIterator[bytes], MimeType | None, str | None, int | None]:
	"""stream file content from storage (access-checked).

	returns (stream, content_type, filename, size_bytes).
	"""
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.READER,
	)
	file = await _get_file(file_id, session)
	try:
		stream, content_type, size_bytes = await read_content(file)
	except FileNotFoundError:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file content not found in storage",
		)
	return stream, content_type, file.filename, size_bytes


async def get_file_url(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	expires_in: int | None = None,
) -> str | None:
	"""get a direct/presigned URL for the file, or None if unsupported."""
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.READER,
	)
	file = await _get_file(file_id, session)
	backend = get_storage_backend(file.storage_backend)
	return await backend.get_url(file.storage_key, expires_in=expires_in)


def _file_category_predicate(category: FileCategoryFilter) -> ColumnElement[bool]:
	if category == "image":
		return File.mime_type.like("image/%")
	if category == "audio":
		return File.mime_type.like("audio/%")
	if category == "video":
		return File.mime_type.like("video/%")
	return or_(
		File.mime_type.is_(None),
		not_(
			or_(
				File.mime_type.like("image/%"),
				File.mime_type.like("audio/%"),
				File.mime_type.like("video/%"),
			)
		),
	)


def _apply_file_filters(stmt: Select, filters: FileListFilters) -> Select:
	if filters.owner_id is not None:
		stmt = stmt.where(File.owner_id == filters.owner_id)
	if filters.project_id is not None:
		stmt = stmt.join(
			file_project_association,
			File.id == file_project_association.c.file_id,
		).where(file_project_association.c.project_id == filters.project_id)
	if filters.source is not None:
		stmt = stmt.where(File.source == filters.source)
	if filters.category is not None:
		stmt = stmt.where(_file_category_predicate(filters.category))
	return stmt


async def list_files(
	session: AsyncSession,
	principal: Principal,
	filters: FileListFilters | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "created_at",
	sort_dir: SortDir = "desc",
) -> list[File]:
	"""list files accessible by the principal."""
	file_filters = filters or FileListFilters()
	stmt = select(File).where(
		File.deleted_at.is_(None),
		resource_access_predicate(
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		),
	)
	stmt = _apply_file_filters(stmt, file_filters)
	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": File.created_at,
			"updated_at": File.updated_at,
			"filename": File.filename,
			"size_bytes": File.size_bytes,
		},
		tie_breaker=File.id,
	)
	result = await session.execute(
		stmt.offset(skip).limit(limit).options(selectinload(File.projects))
	)
	return list(result.scalars().all())


async def count_files(
	session: AsyncSession,
	principal: Principal,
	filters: FileListFilters | None = None,
) -> FileCounts:
	"""count files accessible by the principal."""
	file_filters = filters or FileListFilters()
	base_stmt = select(File).where(
		File.deleted_at.is_(None),
		resource_access_predicate(
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		),
	)
	base_stmt = _apply_file_filters(base_stmt, file_filters)

	total_result = await session.execute(
		base_stmt.with_only_columns(func.count(File.id)).order_by(None)
	)
	total = total_result.scalar_one()

	category_result = await session.execute(
		base_stmt.with_only_columns(
			func.sum(case((_file_category_predicate("image"), 1), else_=0)),
			func.sum(case((_file_category_predicate("audio"), 1), else_=0)),
			func.sum(case((_file_category_predicate("video"), 1), else_=0)),
			func.sum(case((_file_category_predicate("file"), 1), else_=0)),
		).order_by(None)
	)
	image_count, audio_count, video_count, file_count = category_result.one()

	source_result = await session.execute(
		base_stmt.with_only_columns(File.source, func.count(File.id))
		.group_by(File.source)
		.order_by(None)
	)
	by_source = {str(source): count for source, count in source_result.all()}

	ownership_result = await session.execute(
		base_stmt.with_only_columns(
			func.sum(case((File.owner_id == principal.user_id, 1), else_=0)),
			func.sum(case((File.owner_id != principal.user_id, 1), else_=0)),
		).order_by(None)
	)
	owned_total, shared_total = ownership_result.one()

	return FileCounts(
		total=total,
		owned_total=owned_total or 0,
		shared_total=shared_total or 0,
		by_category={
			"image": image_count or 0,
			"audio": audio_count or 0,
			"video": video_count or 0,
			"file": file_count or 0,
		},
		by_source=by_source,
	)


async def get_file(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> File:
	"""get a file by id (requires reader access)."""
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.READER,
	)
	result = await session.execute(
		select(File)
		.where(File.id == file_id, File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	file = result.scalars().one_or_none()
	if not file:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file


async def get_file_payload(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	use_cache: bool = True,
) -> FileOut:
	"""get a file API payload after resource access is validated."""
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.READER,
	)

	async def load_payload() -> FileOut:
		return FileOut.model_validate(await _get_file_with_projects(file_id, session))

	if not use_cache:
		return await load_payload()
	return await get_or_set_resource_payload_cache(
		ResourceType.FILE,
		file_id,
		FileOut,
		load_payload,
	)


async def update_file(
	file_id: TypeID,
	file_in: FileUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> File:
	"""update file metadata (requires editor access)."""
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.EDITOR,
	)
	file = await _get_file(file_id, session)
	updates = file_in.model_dump(exclude_unset=True, by_alias=True)
	new_project_ids: list[TypeID] | None = updates.pop("project_ids", None)
	changed_project_ids: set[TypeID] = set()
	if new_project_ids is not None:
		for pid in new_project_ids:
			await require_project_access(
				pid,
				session,
				principal,
				required_level=AccessLevel.EDITOR,
			)
		# load current projects so reassignment doesn't trigger lazy IO
		await session.execute(
			select(File).where(File.id == file_id).options(selectinload(File.projects))
		)
		old_project_ids = {project.id for project in file.projects}
		file.projects = await load_projects(new_project_ids, session, principal)
		changed_project_ids = old_project_ids | set(new_project_ids)
	for field, value in updates.items():
		setattr(file, field, value)
	await session.flush()
	result = await session.execute(
		select(File)
		.where(File.id == file_id, File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	file = result.scalars().one()

	await _emit_file_event(
		session,
		event_type=EventType.FILE_UPDATED,
		file_id=file_id,
		user_id=principal.user_id,
		filename=file.filename,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.FILE, file_id)
	if changed_project_ids:
		await invalidate_accessible_users_for_resource(
			ResourceType.FILE, file_id, session
		)
	await invalidate_project_payload_caches(changed_project_ids)
	return file


async def delete_file(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a file (soft or hard based on settings).

	hard deletes also remove bytes from the storage backend.
	"""
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.EDITOR,
	)
	file = await _get_file_with_projects(file_id, session)
	project_ids = {project.id for project in file.projects}
	delete_recipients = await list_accessible_user_ids(
		ResourceType.FILE,
		file_id,
		session,
	)

	if not settings.soft_delete.files:
		await delete_content(file)

	if settings.soft_delete.files:
		file.soft_delete()
	else:
		await session.delete(file)

	await _emit_file_event(
		session,
		event_type=EventType.FILE_DELETED,
		file_id=file_id,
		user_id=principal.user_id,
		origin_session_id=origin_session_id,
		recipient_ids=delete_recipients,
	)
	await invalidate_resource_payload_cache(ResourceType.FILE, file_id)
	await invalidate_accessible_users_for_resource(ResourceType.FILE, file_id, session)
	await invalidate_project_payload_caches(project_ids)
