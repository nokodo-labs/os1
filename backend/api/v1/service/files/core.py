"""service layer for file operations.

layered from lowest to highest level:

- storage primitives (store_file, read_content, delete_content): move
  bytes to/from the backend and own the File row. no events, no caches,
  no async processing, no commit.
- programmatic intake (ingest_file): store_file + announce + enqueue
  async processing. the entry point for agents, tools, and generated
  media that create a brand-new file from raw bytes.
- authenticated HTTP-facing operations (upload_file, register_stored_file,
  get_file_content, ...): add permission checks on top of the above.

the low-level and intake functions accept owner_id directly and skip
access checks, so the caller is responsible for authorization.
"""

import base64
import hashlib
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import case, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import ColumnElement, Select
from sqlalchemy.sql.base import ExecutableOption

from api.models.access_rule import AccessLevel
from api.models.event_types import EventType
from api.models.file import File, FileSource, FileStatus
from api.models.many_to_many import file_project_association
from api.models.project import Project
from api.permissions import ActionPermission, ResourceType
from api.schemas.file import File as FileOut
from api.schemas.file import (
	FileCategoryFilter,
	FileCounts,
	FileCreate,
	FileListFilters,
	FilePrivateInput,
	FileUpdate,
)
from api.settings import settings
from api.storage import get_storage_backend, new_storage_key
from api.storage.base import MimeType
from api.v1.service.authentication import Principal, load_principal_for_user
from api.v1.service.authorization import (
	apply_metadata_write,
	apply_resource_access_list_filters,
	invalidate_accessible_users_for_resource,
	list_accessible_user_ids_for_resources,
	project_private,
	require_permission,
	require_private_write,
	require_project_access,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.files.derived_files import delete_all_derived_file_bytes
from api.v1.service.files.events import emit_file_event
from api.v1.service.files.processing import start_file_processing_task
from api.v1.service.files.vectorization import (
	FILE_SPEC,
	remove_file_vectors,
	replace_all_file_vectors,
	replace_file_description_vectors,
)
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.projects import invalidate_project_payload_caches, load_projects
from api.v1.service.resource_payload_cache import (
	get_or_set_resource_payload_cache,
	invalidate_resource_payload_cache,
)
from nokodo_ai.utils.files import corrected_mime_type
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID, new_typeid


log = logging.getLogger(__name__)

# internal helpers


def _apply_private_file_update(file: File, file_in: FileUpdate) -> None:
	"""apply the private half of a file update to the row."""
	private = file_in.private
	if isinstance(private, FilePrivateInput):
		if isinstance(private.storage_backend, str):
			file.storage_backend = private.storage_backend
		if isinstance(private.storage_key, str):
			file.storage_key = private.storage_key
		if private.checksum_sha256 is None or isinstance(private.checksum_sha256, str):
			file.checksum_sha256 = private.checksum_sha256
	apply_metadata_write(file, file_in.metadata, private)


def _file_load_options(resolve_origin: bool = False) -> tuple[ExecutableOption, ...]:
	options: list[ExecutableOption] = [selectinload(File.projects)]
	if resolve_origin:
		options.append(selectinload(File.origin_message))
	return tuple(options)


async def _get_file(
	file_id: TypeID, session: AsyncSession, include_deleted: bool = False
) -> File:
	"""fetch a file record by id (no access check)."""
	stmt = select(File).where(File.id == file_id)
	if include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	else:
		stmt = stmt.where(File.deleted_at.is_(None))
	result = await session.execute(stmt)
	file = result.scalars().one_or_none()
	if not file:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file


async def _get_file_with_projects(
	file_id: TypeID,
	session: AsyncSession,
	include_deleted: bool = False,
	resolve_origin: bool = False,
) -> File:
	"""fetch a file record with project links by id (no access check)."""
	stmt = (
		select(File)
		.where(File.id == file_id)
		.options(*_file_load_options(resolve_origin))
	)
	if include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	else:
		stmt = stmt.where(File.deleted_at.is_(None))
	result = await session.execute(stmt)
	file = result.scalars().one_or_none()
	if not file:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file


async def _stream_upload(upload: UploadFile) -> AsyncIterator[bytes]:
	"""yield chunks from an UploadFile without loading entire file into memory."""
	while chunk := await upload.read(256 * 1024):
		yield chunk


async def _peek_stream(
	source: AsyncIterator[bytes], peek_bytes: int
) -> tuple[bytes, AsyncIterator[bytes]]:
	"""read the leading bytes of a byte stream without consuming it.

	returns the first peek_bytes (fewer if the stream is shorter) and a new
	iterator that re-emits the buffered chunks followed by the remainder of
	the source, so the stream can still be written in full.
	"""
	it = aiter(source)
	buffered: list[bytes] = []
	head = bytearray()
	while len(head) < peek_bytes:
		try:
			chunk = await anext(it)
		except StopAsyncIteration:
			break
		buffered.append(chunk)
		head.extend(chunk)

	async def rechained() -> AsyncIterator[bytes]:
		for chunk in buffered:
			yield chunk
		async for chunk in it:
			yield chunk

	return bytes(head[:peek_bytes]), rechained()


# low-level storage primitives (no auth, no HTTP deps)


async def store_file(
	session: AsyncSession,
	data: bytes | AsyncIterator[bytes],
	owner_id: TypeID,
	filename: str | None = None,
	content_type: MimeType = "application/octet-stream",
	source: FileSource = FileSource.AGENT_GENERATED,
	project_ids: list[TypeID] | None = None,
	message_id: TypeID | None = None,
	backend_name: str | None = None,
	key_prefix: str | None = None,
) -> File:
	"""write raw bytes to storage and create the File row. nothing else.

	this is the lowest-level persistence primitive: it puts the bytes on
	the storage backend, computes size/checksum, and inserts a flushed
	File record linked to the given projects. it does NOT emit events,
	invalidate caches, enqueue processing, or commit the session.

	callers that want the full intake pipeline (announce + async
	processing) should use ingest_file() instead. callers that need to
	defer or batch processing - such as bulk imports running inside a
	larger transaction - call this directly and trigger processing
	themselves once their unit of work has committed.

	does NOT check access permissions - the caller is responsible
	for authorization in their own context.
	"""
	if backend_name is None:
		backend_name = settings.assets.storage.active_backend
	backend = get_storage_backend(backend_name)

	file_id = new_typeid("file")
	key = new_storage_key(prefix=key_prefix)

	# a declared (often client-supplied) content type can disagree with the
	# actual bytes - e.g. a jpeg labeled image/png - which downstream model
	# providers reject. trust the content signature when it is authoritative.
	# for streamed uploads, peek the leading bytes and re-chain them so the
	# stream is still written in full.
	if isinstance(data, (bytes, bytearray, memoryview)):
		head = bytes(data[:4096])
	else:
		head, data = await _peek_stream(data, 4096)
	corrected = corrected_mime_type(content_type, head)
	if corrected:
		content_type = corrected

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
		origin_message_id=message_id,
		projects=projects,
	)
	session.add(file)
	await session.flush()
	return file


async def ingest_file(
	session: AsyncSession,
	data: bytes | AsyncIterator[bytes],
	owner_id: TypeID,
	filename: str | None = None,
	content_type: MimeType = "application/octet-stream",
	source: FileSource = FileSource.AGENT_GENERATED,
	project_ids: list[TypeID] | None = None,
	message_id: TypeID | None = None,
	backend_name: str | None = None,
	key_prefix: str | None = None,
	origin_session_id: str | None = None,
) -> File:
	"""store a brand-new file from raw bytes and run the full intake pipeline.

	this is the high-level entry point for programmatic file creation
	(agents, tools, generated media, background jobs). it:

	1. persists the bytes + File row via store_file(),
	2. emits a FILE_CREATED lifecycle event,
	3. invalidates affected project payload caches,
	4. enqueues async processing (description + content vectorization).

	does NOT check access permissions - the caller is responsible
	for authorization in their own context. for HTTP uploads use
	upload_file(), which adds permission checks on top of this.
	"""
	file = await store_file(
		session,
		data=data,
		owner_id=owner_id,
		filename=filename,
		content_type=content_type,
		source=source,
		project_ids=project_ids,
		message_id=message_id,
		backend_name=backend_name,
		key_prefix=key_prefix,
	)
	await emit_file_event(
		session,
		event_type=EventType.FILE_CREATED,
		file_id=file.id,
		user_id=owner_id,
		filename=filename,
		project_ids=project_ids or [],
		origin_session_id=origin_session_id,
	)
	await invalidate_project_payload_caches(set(project_ids or []))
	principal = await load_principal_for_user(owner_id, session)
	await start_file_processing_task(
		session,
		principal,
		file.id,
		origin_session_id=origin_session_id,
	)

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


async def read_file_base64(
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
		log.warning("read_file_base64: file %s not found", file_id)
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
			"read_file_base64: access denied for file %s (user %s)",
			file_id,
			principal.user.id,
		)
		return None

	try:
		stream, _, _ = await read_content(file)
	except FileNotFoundError:
		log.warning(
			"read_file_base64: storage object missing for file %s",
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


# authenticated operations (HTTP-facing, access-checked)


async def register_stored_file(
	file_in: FileCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> File:
	"""register a File row for bytes already present in a storage backend.

	unlike store_file()/ingest_file(), this writes no bytes: the caller
	supplies an existing storage_backend + storage_key via FileCreate.
	it creates the record, announces it, and indexes the supplied
	description, but does not enqueue content processing.
	"""
	require_permission(principal, ActionPermission.FILES_CREATE)
	require_permission(principal, ActionPermission.FILES_MANAGE)
	for pid in file_in.project_ids:
		await require_project_access(
			pid,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	private = file_in.private
	data = file_in.model_dump(exclude={"project_ids", "private", "metadata"})
	projects = (
		await load_projects(file_in.project_ids, session, principal)
		if file_in.project_ids
		else []
	)
	# size and checksum describe the BYTES, so they are read off the stored
	# object rather than trusted from the payload - a caller could otherwise
	# register a 2GB blob declaring one byte, and Content-Length would lie.
	backend = get_storage_backend(private.storage_backend)
	info = await backend.stat(private.storage_key)
	if info is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="no stored object at the supplied storage key",
		)
	file = File(
		**data,
		owner_id=principal.user.id,
		storage_backend=private.storage_backend,
		storage_key=private.storage_key,
		size_bytes=info.size,
		checksum_sha256=info.checksum_sha256
		or await backend.checksum_sha256(private.storage_key),
		projects=projects,
	)
	file.set_metadata(public=file_in.metadata, private=private.metadata)
	session.add(file)
	await session.flush()

	await emit_file_event(
		session,
		event_type=EventType.FILE_CREATED,
		file_id=file.id,
		user_id=principal.user.id,
		filename=file.filename,
		project_ids=file_in.project_ids,
		origin_session_id=origin_session_id,
	)
	await invalidate_project_payload_caches(set(file_in.project_ids))
	await replace_file_description_vectors(file, session)
	return file


async def upload_file(
	upload: UploadFile,
	session: AsyncSession,
	principal: Principal,
	project_ids: list[TypeID] | None = None,
	origin_session_id: str | None = None,
) -> File:
	"""upload a file via HTTP multipart and create the record."""
	require_permission(principal, ActionPermission.FILES_CREATE)
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

	return await ingest_file(
		session,
		data=file_data,
		owner_id=principal.user.id,
		filename=upload.filename,
		content_type=content_type,
		source=FileSource.USER_UPLOADED,
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


def _apply_file_filters(
	stmt: Select, filters: FileListFilters, principal: Principal
) -> Select:
	if filters.include_deleted and not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
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
	if filters.q is not None and filters.q.strip():
		pattern = contains_pattern(filters.q.strip())
		stmt = stmt.where(
			or_(
				File.filename.ilike(pattern, escape="\\"),
				File.description.ilike(pattern, escape="\\"),
			)
		)
	return apply_resource_access_list_filters(
		stmt,
		principal,
		ResourceType.FILE,
		filters.access_relationship,
		filters.resolved_access_level,
	)


async def list_files(
	session: AsyncSession,
	principal: Principal,
	filters: FileListFilters | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "created_at",
	sort_dir: SortDir = "desc",
	resolve_origin: bool = False,
) -> list[File]:
	"""list files accessible by the principal."""
	file_filters = filters or FileListFilters()
	include_deleted = file_filters.include_deleted
	stmt = select(File).where(
		resource_access_predicate(
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		),
	)
	if include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	stmt = _apply_file_filters(stmt, file_filters, principal)
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
		stmt.offset(skip).limit(limit).options(*_file_load_options(resolve_origin))
	)
	return list(result.scalars().all())


async def count_files(
	session: AsyncSession,
	principal: Principal,
	filters: FileListFilters | None = None,
) -> FileCounts:
	"""count files accessible by the principal."""
	file_filters = filters or FileListFilters()
	include_deleted = file_filters.include_deleted
	base_stmt = select(File).where(
		resource_access_predicate(
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		),
	)
	if include_deleted:
		base_stmt = base_stmt.execution_options(include_deleted=True)
	base_stmt = _apply_file_filters(base_stmt, file_filters, principal)

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
			func.sum(case((File.owner_id == principal.user.id, 1), else_=0)),
			func.sum(case((File.owner_id != principal.user.id, 1), else_=0)),
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
	resolve_origin: bool = False,
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
		.options(*_file_load_options(resolve_origin))
	)
	file = result.scalars().one_or_none()
	if not file:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file


def file_payloads(files: list[File], principal: Principal) -> list[FileOut]:
	"""project file rows to their API payloads for the principal."""
	return project_private(
		principal,
		ResourceType.FILE,
		[FileOut.from_row(file) for file in files],
	)


async def get_file_payload(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	use_cache: bool = True,
	resolve_origin: bool = False,
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
		return FileOut.from_row(
			await _get_file_with_projects(
				file_id,
				session,
				resolve_origin=resolve_origin,
			)
		)

	# the payload cache is not principal-keyed, so it holds the full payload
	# and projection happens per request on the way out.
	if not use_cache or resolve_origin:
		payload = await load_payload()
	else:
		payload = await get_or_set_resource_payload_cache(
			ResourceType.FILE,
			file_id,
			FileOut,
			load_payload,
		)
	return project_private(principal, ResourceType.FILE, [payload])[0]


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
	require_private_write(principal, ResourceType.FILE, file_in.private)
	file = await _get_file(file_id, session)
	updates = file_in.model_dump(exclude_unset=True, exclude={"private", "metadata"})
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
	_apply_private_file_update(file, file_in)
	await session.flush()
	result = await session.execute(
		select(File)
		.where(File.id == file_id, File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	file = result.scalars().one()

	await emit_file_event(
		session,
		event_type=EventType.FILE_UPDATED,
		file_id=file_id,
		user_id=principal.user.id,
		filename=file.filename,
		project_ids=[project.id for project in file.projects],
		affected_project_ids=changed_project_ids,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.FILE, file_id)
	if changed_project_ids:
		await invalidate_accessible_users_for_resource(ResourceType.FILE, file_id)
	await invalidate_project_payload_caches(changed_project_ids)
	if await FILE_SPEC.should_revectorize(file, file_in, session):
		await replace_all_file_vectors(file, session)
	return file


async def delete_file(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
	permanent: bool = False,
) -> None:
	"""delete a file (soft or hard based on settings).

	hard deletes also remove bytes from the storage backend.
	"""
	if permanent and not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.EDITOR,
		include_deleted=permanent,
	)
	file = await _get_file_with_projects(file_id, session, include_deleted=permanent)
	project_ids = {project.id for project in file.projects}
	delete_recipients = await list_accessible_user_ids_for_resources(
		[(ResourceType.FILE, file_id)], session
	)

	hard_delete = permanent or not settings.soft_delete.files
	if hard_delete:
		await delete_content(file)
		# the FK cascade drops derivative rows; delete their bytes too.
		await delete_all_derived_file_bytes(file.id, session)

	if hard_delete:
		await session.delete(file)
	else:
		file.soft_delete()

	await emit_file_event(
		session,
		event_type=EventType.FILE_DELETED,
		file_id=file_id,
		user_id=principal.user.id,
		project_ids=list(project_ids),
		affected_project_ids=project_ids,
		origin_session_id=origin_session_id,
		recipient_ids=delete_recipients,
	)
	await invalidate_resource_payload_cache(ResourceType.FILE, file_id)
	await invalidate_accessible_users_for_resource(ResourceType.FILE, file_id)
	await invalidate_project_payload_caches(project_ids)
	await remove_file_vectors(str(file_id), session=session)


async def restore_file(
	file_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> File:
	if not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	await require_resource_access(
		file_id,
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.EDITOR,
		include_deleted=True,
	)
	file = await _get_file_with_projects(file_id, session, include_deleted=True)
	if file.deleted_at is None:
		return file
	project_ids = {project.id for project in file.projects}
	file.restore()
	await session.flush()
	await emit_file_event(
		session,
		event_type=EventType.FILE_UPDATED,
		file_id=file_id,
		user_id=principal.user.id,
		filename=file.filename,
		project_ids=[project.id for project in file.projects],
		affected_project_ids=project_ids,
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.FILE, file_id)
	await invalidate_accessible_users_for_resource(ResourceType.FILE, file_id)
	await invalidate_project_payload_caches(project_ids)
	await replace_all_file_vectors(file, session)
	return file
