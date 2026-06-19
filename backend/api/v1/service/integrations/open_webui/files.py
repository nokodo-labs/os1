"""Open WebUI file parsing and import writers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import mimetypes
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, unquote_to_bytes, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.file import File, FileSource, FileStatus
from api.models.message import Message
from api.models.project import Project
from api.open_webui import OpenWebUIClient, OpenWebUIError
from api.settings import OpenWebUIDeployment
from api.v1.service.files import remove_file_vectors, store_file
from api.v1.service.files.content_vectorization import CONTENT_VECTOR_FINGERPRINT_KEY
from api.v1.service.integrations.open_webui.common import (
	ImportSummary,
	_append_missing_projects_to_file,
	_first_str,
	_merge_metadata,
	_owui_field_filter,
	_owui_metadata,
	_owui_metadata_value,
	_owui_origin_filter,
)
from api.v1.service.integrations.open_webui.messages import _file_content_part
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


_OWUI_FILE_PATH_PARTS = ("api", "v1", "files")
_OWUI_FILENAME_KEYS = (
	"filename",
	"name",
	"original_filename",
	"original_name",
	"file_name",
	"title",
)
_OWUI_FILE_PATH_KEYS = ("path", "filepath", "file_path")


def _decode_data_url(url: str) -> tuple[bytes, str | None] | None:
	"""decode a data: URL into its raw bytes and media type, or None if not one."""
	if not url.startswith("data:") or "," not in url:
		return None
	header, payload = url[5:].split(",", 1)
	media_type = header.split(";", 1)[0] or None
	try:
		if ";base64" in header:
			return base64.b64decode(payload, validate=True), media_type
		return unquote_to_bytes(payload), media_type
	except binascii.Error, ValueError:
		return None


def _file_id_from_url(url: str) -> str | None:
	"""extract the Open WebUI file id embedded in a file content URL."""
	parsed = urlparse(url)
	parts = tuple(part for part in parsed.path.split("/") if part)
	if len(parts) >= 4 and parts[:3] == _OWUI_FILE_PATH_PARTS:
		return parts[3]
	return None


def _file_entry_object(file_entry: dict[str, Any]) -> dict[str, Any]:
	"""return the nested file object of a raw file entry, or an empty dict."""
	file_obj = file_entry.get("file")
	return file_obj if isinstance(file_obj, dict) else {}


def _file_entry_id(file_entry: dict[str, Any]) -> str | None:
	"""resolve the Open WebUI file id for a raw file entry, including from its URL."""
	file_obj = _file_entry_object(file_entry)
	file_id = _first_str(file_entry, "id", "file_id") or _first_str(
		file_obj, "id", "file_id"
	)
	if file_id:
		return file_id
	url = _file_entry_url(file_entry)
	return _file_id_from_url(url) if url else None


def _file_entry_url(file_entry: dict[str, Any]) -> str | None:
	"""return the content URL declared by a raw file entry, if any."""
	file_obj = _file_entry_object(file_entry)
	return _first_str(file_entry, "url") or _first_str(file_obj, "url")


def _filename_from_value(value: Any) -> str | None:
	"""derive a safe filename from a path or URL value, or None when unusable."""
	if not isinstance(value, str):
		return None
	cleaned = value.strip()
	if not cleaned:
		return None
	parsed = urlparse(cleaned)
	path = parsed.path if parsed.scheme or parsed.netloc else cleaned
	name = unquote(path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1])
	name = name.strip()
	if not name or name in (".", ".."):
		return None
	return name[:255]


def _filename_from_mapping(mapping: dict[str, Any]) -> str | None:
	"""find the first usable filename across a mapping's known name and path keys."""
	for key in _OWUI_FILENAME_KEYS:
		filename = _filename_from_value(mapping.get(key))
		if filename:
			return filename
	for key in _OWUI_FILE_PATH_KEYS:
		filename = _filename_from_value(mapping.get(key))
		if filename:
			return filename
	return None


def _metadata_containers(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
	"""collect a metadata dict and its nested file/meta/data sub-dicts to search."""
	if metadata is None:
		return []
	containers = [metadata]
	for key in ("file", "meta", "data"):
		value = metadata.get(key)
		if isinstance(value, dict):
			containers.append(value)
	for value in list(containers):
		for key in ("file", "meta", "data"):
			nested = value.get(key)
			if isinstance(nested, dict) and nested not in containers:
				containers.append(nested)
	return containers


def _file_entry_filename(
	file_entry: dict[str, Any],
	metadata: dict[str, Any] | None = None,
) -> str | None:
	"""resolve a file entry's filename from its own fields then its metadata."""
	for mapping in (file_entry, _file_entry_object(file_entry)):
		filename = _filename_from_mapping(mapping)
		if filename:
			return filename
	for mapping in _metadata_containers(metadata):
		filename = _filename_from_mapping(mapping)
		if filename:
			return filename
	return None


def _file_entry_fallback_filename(
	owui_file_id: str | None,
	url: str | None,
	media_type: str | None,
) -> str:
	"""build a deterministic filename when the source provides none."""
	url_name = (
		_filename_from_value(url) if url and not url.startswith("data:") else None
	)
	if url_name and url_name != "content":
		return url_name
	extension = mimetypes.guess_extension(media_type or "") or ""
	if extension == ".jpe":
		extension = ".jpg"
	stem = (
		f"open-webui-{owui_file_id}"
		if owui_file_id is not None
		else "open-webui-attachment"
	)
	return f"{stem}{extension}"[:255]


def _file_entry_media_type(
	file_entry: dict[str, Any],
	metadata: dict[str, Any] | None = None,
	response_media_type: str | None = None,
) -> str | None:
	"""resolve a file entry's media type from its fields, metadata, or response."""
	file_obj = _file_entry_object(file_entry)
	meta = metadata.get("meta") if metadata else None
	data = metadata.get("data") if metadata else None
	if not isinstance(meta, dict):
		meta = {}
	if not isinstance(data, dict):
		data = {}
	entry_type = _first_str(file_entry, "media_type", "content_type", "mime_type")
	if entry_type and "/" in entry_type:
		return entry_type
	return (
		response_media_type
		or _first_str(file_obj, "media_type", "content_type", "mime_type")
		or _first_str(meta, "content_type", "mime_type")
		or _first_str(data, "content_type", "mime_type")
	)


async def _collapse_file_duplicates(
	session: AsyncSession,
	matches: list[File],
) -> File | None:
	"""keep the oldest match and soft-delete any extra duplicate rows.

	earlier buggy imports created several rows for the same logical file. once
	we can identify them by a stable key, re-import collapses them: the oldest
	survives as canonical and the rest are soft-deleted with their vectors
	removed. the re-import rebuilds the message content to point at the
	survivor, so references to the dropped rows are superseded.
	"""
	if not matches:
		return None
	canonical = matches[0]
	for loser in matches[1:]:
		loser.deleted_at = datetime.now(tz=UTC)
		await remove_file_vectors(str(loser.id), session)
	return canonical


def _mark_file_for_reprocessing(file: File) -> None:
	"""flag a healed file whose content processing inputs changed.

	healing can populate a previously-null mime type or filename, which changes
	how the file routes through text extraction. clearing the recorded
	fingerprint and description, and resetting status to PENDING, makes the
	maintenance sweep redo processing with the corrected routing.
	"""
	metadata = dict(file.metadata_ or {})
	metadata.pop(CONTENT_VECTOR_FINGERPRINT_KEY, None)
	file.metadata_ = metadata
	file.description = None
	file.status = FileStatus.PENDING


async def _find_file_for_owui_id(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	owui_file_id: str,
) -> File | None:
	"""find the canonical imported file for an Open WebUI id, collapsing duplicates."""
	result = await session.scalars(
		select(File)
		.where(
			File.owner_id == owner_id,
			File.deleted_at.is_(None),
			File.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(File.metadata_, deployment),
			_owui_field_filter(File.metadata_, "file_id", owui_file_id),
		)
		.options(selectinload(File.projects))
		.order_by(File.created_at.asc())
	)
	return await _collapse_file_duplicates(session, list(result.all()))


async def _find_file_by_checksum(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	message_id: TypeID,
	checksum_sha256: str,
) -> File | None:
	"""find the canonical imported file matching a byte checksum, collapsing duplicates.

	id-less inline attachments (data: URLs) carry no Open WebUI id or filename, so
	byte checksum scoped to (owner, message, origin) is the only stable identity
	for dedup/heal across re-imports.
	"""
	result = await session.scalars(
		select(File)
		.where(
			File.owner_id == owner_id,
			File.message_id == message_id,
			File.checksum_sha256 == checksum_sha256,
			File.deleted_at.is_(None),
			File.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(File.metadata_, deployment),
		)
		.options(selectinload(File.projects))
		.order_by(File.created_at.asc())
	)
	return await _collapse_file_duplicates(session, list(result.all()))


def _heal_existing_file(
	existing: File,
	*,
	file_entry: dict[str, Any],
	url: str | None,
	message_id: TypeID,
	projects: list[Project],
	deployment: OpenWebUIDeployment,
	owui_file_id: str | None,
	metadata_fields: dict[str, Any],
	source_metadata: dict[str, Any] | None,
) -> None:
	"""repair a previously-imported file row in place from a fresh import's data."""
	routing_changed = False
	if existing.mime_type is None:
		media_type = _file_entry_media_type(file_entry, source_metadata)
		if media_type is not None:
			existing.mime_type = media_type
			routing_changed = True
	if existing.filename is None:
		filename = _file_entry_filename(
			file_entry,
			source_metadata,
		) or _file_entry_fallback_filename(owui_file_id, url, existing.mime_type)
		existing.filename = filename
		routing_changed = routing_changed or filename is not None
	_append_missing_projects_to_file(existing, projects)
	if existing.message_id is None:
		existing.message_id = message_id
	existing.metadata_ = _merge_metadata(
		existing.metadata_,
		_owui_metadata(deployment, "file", owui_file_id, **metadata_fields),
	)
	if routing_changed:
		_mark_file_for_reprocessing(existing)


async def _import_file_entry(
	file_entry: dict[str, Any],
	client: OpenWebUIClient,
	session: AsyncSession,
	owner_id: TypeID,
	message_id: TypeID,
	chat_id: str,
	owui_message_id: str,
	projects: list[Project],
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> dict[str, Any] | None:
	"""import or heal one Open WebUI file entry and return its message content part."""
	owui_file_id = _file_entry_id(file_entry)
	url = _file_entry_url(file_entry)
	metadata: dict[str, Any] | None = None
	data: bytes | None = None
	response_media_type: str | None = None
	project_ids = [TypeID(project.id) for project in projects]
	metadata_fields = {
		key: value
		for key, value in (
			("file_id", owui_file_id),
			("chat_id", chat_id),
			("message_id", owui_message_id),
		)
		if value is not None
	}

	if owui_file_id:
		existing = await _find_file_for_owui_id(
			session=session,
			owner_id=owner_id,
			deployment=deployment,
			owui_file_id=owui_file_id,
		)
		if existing is not None:
			existing_metadata: dict[str, Any] | None = None
			if existing.filename is None or existing.mime_type is None:
				try:
					existing_metadata = await client.get_file_metadata(owui_file_id)
				except OpenWebUIError:
					existing_metadata = None
			_heal_existing_file(
				existing,
				file_entry=file_entry,
				url=url,
				message_id=message_id,
				projects=projects,
				deployment=deployment,
				owui_file_id=owui_file_id,
				metadata_fields=metadata_fields,
				source_metadata=existing_metadata,
			)
			summary.files_skipped += 1
			return _file_content_part(
				file_id=TypeID(existing.id),
				url=None,
				filename=existing.filename,
				media_type=existing.mime_type,
				owui_file_id=owui_file_id,
				checksum_sha256=existing.checksum_sha256,
			)

	if owui_file_id:
		try:
			metadata = await client.get_file_metadata(owui_file_id)
			data, response_media_type = await client.download_file(owui_file_id)
		except OpenWebUIError as exc:
			summary.files_skipped += 1
			summary.add_error(f"file {owui_file_id} skipped: {exc}")
	elif url:
		decoded = _decode_data_url(url)
		if decoded:
			data, response_media_type = decoded

	checksum_sha256 = hashlib.sha256(data).hexdigest() if data is not None else None

	# id-less inline attachments dedup/heal by byte checksum scoped to the
	# owning message (the only stable identity they carry).
	if owui_file_id is None and checksum_sha256 is not None:
		existing = await _find_file_by_checksum(
			session=session,
			owner_id=owner_id,
			deployment=deployment,
			message_id=message_id,
			checksum_sha256=checksum_sha256,
		)
		if existing is not None:
			_heal_existing_file(
				existing,
				file_entry=file_entry,
				url=url,
				message_id=message_id,
				projects=projects,
				deployment=deployment,
				owui_file_id=None,
				metadata_fields=metadata_fields,
				source_metadata=metadata,
			)
			summary.files_skipped += 1
			return _file_content_part(
				file_id=TypeID(existing.id),
				url=None,
				filename=existing.filename,
				media_type=existing.mime_type,
				owui_file_id=None,
				checksum_sha256=existing.checksum_sha256,
			)

	filename = _file_entry_filename(file_entry, metadata)
	media_type = _file_entry_media_type(
		file_entry,
		metadata,
		response_media_type=response_media_type,
	)
	if media_type is None and filename:
		media_type = mimetypes.guess_type(filename)[0]
	media_type = media_type or "application/octet-stream"
	filename = filename or _file_entry_fallback_filename(
		owui_file_id,
		url,
		media_type,
	)

	if data is None:
		return _file_content_part(
			file_id=None,
			url=url,
			filename=filename,
			media_type=media_type,
			owui_file_id=owui_file_id,
		)

	try:
		file = await store_file(
			session=session,
			data=data,
			owner_id=owner_id,
			filename=filename,
			content_type=media_type,
			source=FileSource.IMPORT,
			project_ids=project_ids,
			message_id=message_id,
		)
	except (OSError, RuntimeError, ValueError) as exc:
		summary.files_skipped += 1
		file_label = owui_file_id or filename or url or "attachment"
		summary.add_error(f"file {file_label} skipped: {exc}")
		logger.warning("Open WebUI file import skipped: %s", exc)
		fallback_url = url if url and not url.startswith("data:") else None
		return _file_content_part(
			file_id=None,
			url=fallback_url,
			filename=filename,
			media_type=media_type,
			owui_file_id=owui_file_id,
		)
	file.metadata_ = _merge_metadata(
		file.metadata_,
		_owui_metadata(deployment, "file", owui_file_id, **metadata_fields),
	)
	summary.files_imported += 1
	return _file_content_part(
		file_id=file.id,
		url=None,
		filename=file.filename,
		media_type=file.mime_type,
		owui_file_id=owui_file_id,
		checksum_sha256=file.checksum_sha256,
	)


async def _append_file_parts(
	message: Message,
	raw_files: Iterable[dict[str, Any]],
	client: OpenWebUIClient,
	session: AsyncSession,
	owner_id: TypeID,
	chat_id: str,
	owui_message_id: str,
	projects: list[Project],
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> None:
	"""import a message's file entries, healing and deduplicating its content parts."""
	# rebuild content keeping one slot per stable identity (Open WebUI file id,
	# byte checksum, then our file id). older buggy imports could append several
	# parts for one logical file, so collapse those down first; then a re-import
	# heals the surviving slot in place - pointing it at the canonical row -
	# instead of leaving a stale reference and appending yet another duplicate.
	# _import_file_entry still runs for every entry so its heal/collapse path
	# repairs the File rows behind those parts.
	original = list(message.content or [])
	content: list[Any] = []
	index_by_key: dict[str, int] = {}
	for content_part in original:
		key = _content_part_dedup_key(content_part)
		if key is not None and key in index_by_key:
			continue
		if key is not None:
			index_by_key[key] = len(content)
		content.append(content_part)
	changed = len(content) != len(original)
	for file_entry in raw_files:
		file_part = await _import_file_entry(
			file_entry,
			client=client,
			session=session,
			owner_id=owner_id,
			message_id=TypeID(message.id),
			chat_id=chat_id,
			owui_message_id=owui_message_id,
			projects=projects,
			deployment=deployment,
			summary=summary,
		)
		if file_part is None:
			continue
		key = _content_part_dedup_key(file_part)
		if key is not None and key in index_by_key:
			position = index_by_key[key]
			if content[position] != file_part:
				content[position] = file_part
				changed = True
			continue
		if key is not None:
			index_by_key[key] = len(content)
		content.append(file_part)
		changed = True
	if changed:
		message.content = content


def _content_part_dedup_key(content_part: Any) -> str | None:
	"""build a stable identity key for a message content part, or None when absent."""
	# priority orders identity by stability across re-imports: the Open WebUI id
	# and byte checksum survive buggy imports that minted several local rows,
	# while our local file id is per-row and so least stable for healing.
	if not isinstance(content_part, dict):
		return None
	metadata = content_part.get("metadata")
	if isinstance(metadata, dict):
		owui_file_id = _owui_metadata_value(metadata, "file_id")
		if isinstance(owui_file_id, str) and owui_file_id:
			return f"owui:{owui_file_id}"
		checksum = metadata.get("checksum_sha256")
		if isinstance(checksum, str) and checksum:
			return f"sha:{checksum}"
		file_id = metadata.get("file_id")
		if isinstance(file_id, str) and file_id:
			return f"file:{file_id}"
	url = content_part.get("url")
	if isinstance(url, str) and url:
		return f"url:{url}"
	return None
