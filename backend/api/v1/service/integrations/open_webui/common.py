"""shared types and parsing helpers used across Open WebUI resource importers."""

from __future__ import annotations

import json
import mimetypes
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from api.models.file import File
from api.models.message import Message
from api.models.project import Project
from api.models.thread import Thread
from api.open_webui import OpenWebUIAuthError, OpenWebUIError
from api.settings import OpenWebUIDeployment
from api.v1.service.integrations.open_webui.deployments import normalize_origin
from nokodo_ai.types.json import JSONValue
from nokodo_ai.utils.typeid import TypeID


OWUI_METADATA_KEY = "open-webui"


@dataclass(slots=True)
class ImportSummary:
	"""result of an Open WebUI import run."""

	deployment_origin: str
	chats_imported: int = 0
	chats_skipped: int = 0
	messages_imported: int = 0
	projects_imported: int = 0
	projects_skipped: int = 0
	files_imported: int = 0
	files_skipped: int = 0
	memories_imported: int = 0
	memories_skipped: int = 0
	notes_imported: int = 0
	notes_skipped: int = 0
	errors: list[str] | None = None
	# resources created during this run that still need vectorization; the
	# import vectorizes them only after its transaction has committed.
	memory_ids: list[TypeID] = field(default_factory=list)
	note_ids: list[TypeID] = field(default_factory=list)
	thread_ids: list[TypeID] = field(default_factory=list)

	def add_error(self, msg: str) -> None:
		if self.errors is None:
			self.errors = []
		self.errors.append(msg)


def _coerce_json_value(value: Any) -> JSONValue:
	if isinstance(value, str):
		stripped = value.strip()
		if not stripped:
			return ""
		try:
			return _coerce_json_value(json.loads(stripped))
		except json.JSONDecodeError:
			return value
	if value is None or isinstance(value, bool | int | float | str):
		return value
	if isinstance(value, dict):
		return {str(key): _coerce_json_value(item) for key, item in value.items()}
	if isinstance(value, list):
		return [_coerce_json_value(item) for item in value]
	return str(value)


def _json_attr(value: str | None) -> JSONValue:
	if value is None or value.strip() == "":
		return {}
	return _coerce_json_value(value)


def _first_str(mapping: dict[str, Any], *keys: str) -> str | None:
	for key in keys:
		value = mapping.get(key)
		if isinstance(value, str) and value:
			return value
	return None


def _looks_like_image(media_type: str | None, filename: str | None) -> bool:
	if media_type and media_type.startswith("image/"):
		return True
	if not filename:
		return False
	guessed, _ = mimetypes.guess_type(filename)
	return bool(guessed and guessed.startswith("image/"))


def _epoch_to_dt(value: Any) -> datetime | None:
	"""coerce an Open WebUI timestamp value to a UTC datetime."""
	if value in (None, 0, "0"):
		return None
	if isinstance(value, str):
		stripped = value.strip()
		if not stripped or stripped == "0":
			return None
		try:
			return _epoch_to_dt(float(stripped))
		except ValueError:
			pass
		try:
			parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
		except ValueError:
			return None
		if parsed.tzinfo is None:
			return parsed.replace(tzinfo=UTC)
		return parsed.astimezone(UTC)
	try:
		epoch = float(value)
		if abs(epoch) >= 100_000_000_000_000_000:
			epoch = epoch / 1_000_000_000
		elif abs(epoch) >= 100_000_000_000:
			epoch = epoch / 1000
		return datetime.fromtimestamp(epoch, tz=UTC)
	except TypeError, ValueError, OverflowError, OSError:
		return None


def _first_dt(mapping: dict[str, Any], *keys: str) -> datetime | None:
	for key in keys:
		value = _epoch_to_dt(mapping.get(key))
		if value is not None:
			return value
	return None


def _message_timestamp(msg: dict[str, Any]) -> datetime | None:
	return _first_dt(msg, "timestamp", "created_at", "updated_at")


def _chat_created_at(
	chat: dict[str, Any],
	chat_body: dict[str, Any],
) -> datetime | None:
	return _first_dt(chat, "created_at", "createdAt") or _first_dt(
		chat_body,
		"created_at",
		"createdAt",
	)


def _chat_updated_at(
	chat: dict[str, Any],
	chat_body: dict[str, Any],
	owui_messages: dict[str, dict[str, Any]],
) -> datetime | None:
	candidates = [
		_first_dt(chat, "updated_at", "updatedAt", "last_activity_at", "timestamp"),
		_first_dt(
			chat_body,
			"updated_at",
			"updatedAt",
			"last_activity_at",
			"timestamp",
		),
	]
	candidates.extend(_message_timestamp(message) for message in owui_messages.values())
	return max(
		(candidate for candidate in candidates if candidate is not None),
		default=None,
	)


def _owui_origin(deployment: OpenWebUIDeployment) -> str:
	return normalize_origin(str(deployment.origin))


def _owui_metadata(
	deployment: OpenWebUIDeployment,
	resource_type: str,
	owui_id: str | None,
	**fields: Any,
) -> dict[str, Any]:
	open_webui: dict[str, Any] = {
		"origin": _owui_origin(deployment),
		"resource_type": resource_type,
	}
	if owui_id is not None:
		open_webui["id"] = owui_id
	for key, value in fields.items():
		open_webui[key.removeprefix("owui_")] = value
	return {"imported_from": "open_webui", OWUI_METADATA_KEY: open_webui}


def _merge_metadata(
	current: dict[str, Any] | None,
	metadata: dict[str, Any],
) -> dict[str, Any]:
	current_metadata = dict(current or {})
	next_metadata = dict(metadata)
	current_open_webui = current_metadata.get(OWUI_METADATA_KEY)
	next_open_webui = next_metadata.get(OWUI_METADATA_KEY)
	merged = {**current_metadata, **next_metadata}
	if isinstance(current_open_webui, dict) or isinstance(next_open_webui, dict):
		merged[OWUI_METADATA_KEY] = {
			**(current_open_webui if isinstance(current_open_webui, dict) else {}),
			**(next_open_webui if isinstance(next_open_webui, dict) else {}),
		}
	return merged


def _owui_metadata_value(metadata: dict[str, Any] | None, key: str) -> Any:
	if metadata is None:
		return None
	open_webui = metadata.get(OWUI_METADATA_KEY)
	if isinstance(open_webui, dict) and key in open_webui:
		return open_webui.get(key)
	return None


def _owui_origin_filter(metadata_column: Any, deployment: OpenWebUIDeployment) -> Any:
	return metadata_column[OWUI_METADATA_KEY]["origin"].as_string() == _owui_origin(
		deployment
	)


def _owui_field_filter(metadata_column: Any, key: str, value: str) -> Any:
	return metadata_column[OWUI_METADATA_KEY][key].as_string() == value


def _metadata_part_index(value: Any) -> int | None:
	if isinstance(value, int):
		return value
	if isinstance(value, str):
		try:
			return int(value)
		except ValueError:
			return None
	return None


def _metadata_message_id(message: Message) -> str | None:
	value = _owui_metadata_value(message.metadata_, "message_id")
	return value if isinstance(value, str) and value else None


def _append_missing_projects_to_thread(
	thread: Thread, projects: Iterable[Project]
) -> None:
	existing_ids = {str(project.id) for project in thread.projects}
	for project in projects:
		project_id = str(project.id)
		if project_id in existing_ids:
			continue
		thread.projects.append(project)
		existing_ids.add(project_id)


def _append_missing_projects_to_file(file: File, projects: Iterable[Project]) -> None:
	existing_ids = {str(project.id) for project in file.projects}
	for project in projects:
		project_id = str(project.id)
		if project_id in existing_ids:
			continue
		file.projects.append(project)
		existing_ids.add(project_id)


def _unique_projects(projects: Iterable[Project]) -> list[Project]:
	unique: list[Project] = []
	seen: set[str] = set()
	for project in projects:
		project_id = str(project.id)
		if project_id in seen:
			continue
		unique.append(project)
		seen.add(project_id)
	return unique


def _iter_tag_values(value: Any) -> Iterable[str]:
	if isinstance(value, str):
		yield value
	elif isinstance(value, list):
		for item in value:
			if isinstance(item, str):
				yield item
			elif isinstance(item, dict):
				name = _first_str(item, "name", "label", "id")
				if name:
					yield name


def _normalize_chat_tag(value: str) -> str | None:
	cleaned = " ".join(value.strip().split()).lower().replace(" ", "_")
	cleaned = cleaned.strip("#_")
	if not cleaned or cleaned == "none":
		return None
	return cleaned[:50]


def _client_error_to_http_exception(exc: OpenWebUIError) -> HTTPException:
	if isinstance(exc, OpenWebUIAuthError):
		return HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Open WebUI rejected the provided credential",
		)
	return HTTPException(
		status_code=status.HTTP_502_BAD_GATEWAY,
		detail=str(exc) or "Open WebUI request failed",
	)
