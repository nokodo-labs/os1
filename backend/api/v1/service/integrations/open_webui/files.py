"""Open WebUI file parsing and import writers."""

from __future__ import annotations

import base64
import binascii
import logging
import mimetypes
from collections.abc import Iterable
from typing import Any
from urllib.parse import unquote, unquote_to_bytes, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.file import File, FileSource
from api.models.message import Message
from api.models.project import Project
from api.open_webui import OpenWebUIClient, OpenWebUIError
from api.settings import OpenWebUIDeployment
from api.v1.service.files import store_file
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
	if not url.startswith("data:") or "," not in url:
		return None
	header, payload = url[5:].split(",", 1)
	media_type = header.split(";", 1)[0] or None
	try:
		if ";base64" in header:
			return base64.b64decode(payload, validate=True), media_type
		return unquote_to_bytes(payload), media_type
	except (binascii.Error, ValueError):
		return None


def _file_id_from_url(url: str) -> str | None:
	parsed = urlparse(url)
	parts = tuple(part for part in parsed.path.split("/") if part)
	if len(parts) >= 4 and parts[:3] == _OWUI_FILE_PATH_PARTS:
		return parts[3]
	return None


def _file_entry_object(file_entry: dict[str, Any]) -> dict[str, Any]:
	file_obj = file_entry.get("file")
	return file_obj if isinstance(file_obj, dict) else {}


def _file_entry_id(file_entry: dict[str, Any]) -> str | None:
	file_obj = _file_entry_object(file_entry)
	file_id = _first_str(file_entry, "id", "file_id") or _first_str(
		file_obj, "id", "file_id"
	)
	if file_id:
		return file_id
	url = _file_entry_url(file_entry)
	return _file_id_from_url(url) if url else None


def _file_entry_url(file_entry: dict[str, Any]) -> str | None:
	file_obj = _file_entry_object(file_entry)
	return _first_str(file_entry, "url") or _first_str(file_obj, "url")


def _filename_from_value(value: Any) -> str | None:
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
) -> str | None:
	url_name = (
		_filename_from_value(url) if url and not url.startswith("data:") else None
	)
	if url_name and url_name != "content":
		return url_name
	if owui_file_id is None:
		return None
	extension = mimetypes.guess_extension(media_type or "") or ""
	if extension == ".jpe":
		extension = ".jpg"
	return f"open-webui-{owui_file_id}{extension}"[:255]


def _file_entry_media_type(
	file_entry: dict[str, Any],
	metadata: dict[str, Any] | None = None,
	response_media_type: str | None = None,
) -> str | None:
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


async def _find_file_for_owui_id(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	owui_file_id: str,
) -> File | None:
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
		.limit(1)
	)
	return result.one_or_none()


async def _import_file_entry(
	file_entry: dict[str, Any],
	client: OpenWebUIClient,
	session: AsyncSession,
	owner_id: TypeID,
	message_id: TypeID,
	projects: list[Project],
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> dict[str, Any] | None:
	owui_file_id = _file_entry_id(file_entry)
	url = _file_entry_url(file_entry)
	metadata: dict[str, Any] | None = None
	data: bytes | None = None
	response_media_type: str | None = None
	project_ids = [TypeID(project.id) for project in projects]

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
			if existing.mime_type is None:
				existing_media_type = _file_entry_media_type(
					file_entry, existing_metadata
				)
				if existing_media_type is not None:
					existing.mime_type = existing_media_type
			if existing.filename is None:
				existing.filename = _file_entry_filename(
					file_entry,
					existing_metadata,
				) or _file_entry_fallback_filename(
					owui_file_id,
					url,
					existing.mime_type,
				)
			_append_missing_projects_to_file(existing, projects)
			if existing.message_id is None:
				existing.message_id = message_id
			existing.metadata_ = _merge_metadata(
				existing.metadata_,
				_owui_metadata(deployment, "file", owui_file_id, file_id=owui_file_id),
			)
			summary.files_skipped += 1
			return _file_content_part(
				file_id=TypeID(existing.id),
				url=None,
				filename=existing.filename,
				media_type=existing.mime_type,
				owui_file_id=owui_file_id,
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
		_owui_metadata(deployment, "file", owui_file_id, file_id=owui_file_id),
	)
	summary.files_imported += 1
	# imported attachments are stored inside the import's nested transaction;
	# defer async processing until after the whole import has committed.
	summary.processing_file_ids.append(file.id)
	return _file_content_part(
		file_id=file.id,
		url=None,
		filename=file.filename,
		media_type=file.mime_type,
		owui_file_id=owui_file_id,
	)


async def _append_file_parts(
	message: Message,
	raw_files: Iterable[dict[str, Any]],
	client: OpenWebUIClient,
	session: AsyncSession,
	owner_id: TypeID,
	projects: list[Project],
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> None:
	seen: set[str] = set()
	for content_part in message.content or []:
		metadata = (
			content_part.get("metadata") if isinstance(content_part, dict) else None
		)
		existing_file_id = None
		if isinstance(metadata, dict):
			existing_file_id = _owui_metadata_value(metadata, "file_id")
		if isinstance(existing_file_id, str) and existing_file_id:
			seen.add(existing_file_id)
		elif isinstance(content_part, dict):
			url = content_part.get("url")
			if isinstance(url, str) and url:
				seen.add(url)
	for file_entry in raw_files:
		key = _file_entry_id(file_entry) or _file_entry_url(file_entry)
		if key is not None:
			if key in seen:
				continue
			seen.add(key)
		file_part = await _import_file_entry(
			file_entry,
			client=client,
			session=session,
			owner_id=owner_id,
			message_id=TypeID(message.id),
			projects=projects,
			deployment=deployment,
			summary=summary,
		)
		if file_part is not None:
			message.content = [*(message.content or []), file_part]
