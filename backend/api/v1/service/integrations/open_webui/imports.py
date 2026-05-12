"""Open WebUI import service."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import mimetypes
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import unquote, unquote_to_bytes, urlparse

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.agent import Agent
from api.models.file import File, FileSource
from api.models.memory import Memory
from api.models.message import Message, MessageType
from api.models.note import Note
from api.models.project import Project
from api.models.thread import Thread
from api.open_webui import OpenWebUIAuthError, OpenWebUIClient, OpenWebUIError
from api.permissions import ActionPermission
from api.settings import OpenWebUIDeployment
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.files import store_file
from api.v1.service.integrations.open_webui.deployments import (
	get_deployment,
	normalize_origin,
)
from api.v1.service.threads import ensure_participant
from nokodo_ai.types.json import JSONValue
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_OWUI_FILE_PATH_PARTS = ("api", "v1", "files")
_OWUI_METADATA_KEY = "open-webui"
_OWUI_FILENAME_KEYS = (
	"filename",
	"name",
	"original_filename",
	"original_name",
	"file_name",
	"title",
)
_OWUI_FILE_PATH_KEYS = ("path", "filepath", "file_path")
_PINNED_CHATS_PROJECT_NAME = "pinned chats"
_CHAT_FETCH_BATCH_SIZE = 24
_OWUI_PLACEHOLDER_CHAT_TITLES = frozenset(
	{
		"asqerdec amaynut",
		"bag-ong diskusyon",
		"comhrá nua",
		"conversație nouă",
		"دردشة جديدة",
		"گپ جدید",
		"צ'אט חדש",
		"नई चैट",
		"نئی بات چیت",
		"ਨਵੀਂ ਗੱਲਬਾਤ",
		"يېڭى سۆھبەت",
		"new chat",
		"new bark",
		"neuer chat",
		"nieuwe chat",
		"nou xat",
		"nova conversa",
		"nová konverzace",
		"nový chat",
		"novo chat",
		"novi razgovor",
		"ново ћаскање",
		"nowy czat",
		"nuova chat",
		"nouvelle conversation",
		"nuevo chat",
		"ny chat",
		"ny chatt",
		"obrolan baru",
		"perbualan baru",
		"tạo chat mới",
		"txat berria",
		"uusi keskustelu",
		"uus vestlus",
		"új beszélgetés",
		"yangi chat",
		"yeni sohbet",
		"yeni çat",
		"新增對話",
		"新对话",
		"янги чат",
		"новий чат",
		"แชทใหม่",
		"புதிய அரட்டை",
		"новый чат",
		"jauna tērzēšana",
		"naujas pokalbis",
		"새 채팅",
		"ახალი მიმოწერა",
		"新しいチャット",
		"νέα συνομιλία",
		"ཁ་བརྡ་གསར་པ།",
		"নতুন চ্যাট",
		"нов чат",
	}
)

type ImportProgressCallback = Callable[[int, str], Awaitable[None]]
type ChatImportMode = Literal["batched", "bulk"]


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


def _file_content_part(
	file_id: TypeID | None,
	url: str | None,
	filename: str | None,
	media_type: str | None,
	owui_file_id: str | None,
) -> dict[str, Any] | None:
	if file_id is None and not url:
		return None
	metadata: dict[str, Any] = {
		"imported_from": "open_webui",
		"attachment_status": "active",
	}
	if file_id is not None:
		metadata["file_id"] = str(file_id)
	if owui_file_id is not None:
		metadata[_OWUI_METADATA_KEY] = {"file_id": owui_file_id}
	part: dict[str, Any] = {
		"type": "image" if _looks_like_image(media_type, filename) else "file",
		"filename": filename,
		"media_type": media_type,
		"metadata": metadata,
	}
	if url and file_id is None:
		part["url"] = url
	return part


def _content_value_parts(value: Any) -> list[dict[str, Any]]:
	parts: list[dict[str, Any]] = []
	if isinstance(value, str) and value.strip():
		parts.append({"type": "text", "text": value})
	elif isinstance(value, list):
		for block in value:
			if not isinstance(block, dict):
				continue
			text = block.get("text")
			if isinstance(text, str) and text:
				parts.append({"type": "text", "text": text})
				continue

			block_type = block.get("type")
			if block_type in ("input_text", "output_text"):
				input_text = block.get("text")
				if isinstance(input_text, str) and input_text:
					parts.append({"type": "text", "text": input_text})
				continue

			image_url = block.get("image_url")
			if isinstance(image_url, dict):
				image_url = image_url.get("url")
			if isinstance(image_url, str) and image_url:
				parts.append({"type": "image", "url": image_url})
				continue

			url = block.get("url")
			if isinstance(url, str) and url:
				media_type = _first_str(
					block, "media_type", "content_type", "mime_type"
				)
				filename = _first_str(block, "filename", "name")
				parts.append(
					{
						"type": "image"
						if _looks_like_image(media_type, filename)
						else "file",
						"url": url,
						"filename": filename,
						"media_type": media_type,
					}
				)
	return parts


def _tool_call_from_owui(raw: dict[str, Any]) -> dict[str, Any] | None:
	call_id = _first_str(raw, "id", "call_id")
	function = raw.get("function")
	if isinstance(function, dict):
		name = _first_str(function, "name")
		arguments = function.get("arguments")
	else:
		name = _first_str(raw, "name")
		arguments = raw.get("parameters")
		if arguments is None:
			arguments = raw.get("arguments")
	if not call_id:
		call_id = f"owui_tool_{abs(hash(json.dumps(raw, sort_keys=True, default=str)))}"
	if not name:
		return None
	return {
		"id": call_id,
		"name": name,
		"arguments": _coerce_json_value(arguments if arguments is not None else {}),
	}


class _ToolDetailsHTMLParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.text_parts: list[str] = []
		self.blocks: list[ToolDetailsBlock] = []
		self._active_attrs: dict[str, str] | None = None
		self._active_output: list[str] = []
		self._details_depth = 0
		self._summary_depth = 0

	def handle_starttag(
		self,
		tag: str,
		attrs: list[tuple[str, str | None]],
	) -> None:
		attr_map = {key: value or "" for key, value in attrs}
		if tag == "details" and attr_map.get("type") == "tool_calls":
			self._active_attrs = attr_map
			self._active_output = []
			self._details_depth = 1
			self._summary_depth = 0
			return
		if self._active_attrs is None:
			return
		if tag == "details":
			self._details_depth += 1
		elif tag == "summary":
			self._summary_depth += 1

	def handle_endtag(self, tag: str) -> None:
		if self._active_attrs is None:
			return
		if tag == "summary" and self._summary_depth > 0:
			self._summary_depth -= 1
			return
		if tag != "details":
			return
		self._details_depth -= 1
		if self._details_depth > 0:
			return

		attrs = self._active_attrs
		files_value = _json_attr(attrs.get("files"))
		files = files_value if isinstance(files_value, list) else []
		self.blocks.append(
			ToolDetailsBlock(
				call_id=attrs.get("id") or "owui_tool_call",
				name=attrs.get("name") or "tool",
				arguments=_json_attr(attrs.get("arguments")),
				output="".join(self._active_output).strip(),
				files=[item for item in files if isinstance(item, dict)],
				is_error=attrs.get("done") == "error",
			)
		)
		self._active_attrs = None
		self._active_output = []

	def handle_data(self, data: str) -> None:
		if self._active_attrs is None:
			self.text_parts.append(data)
		elif self._summary_depth == 0:
			self._active_output.append(data)


def _parse_tool_details(content: str) -> tuple[str, list[ToolDetailsBlock]]:
	if "<details" not in content or "tool_calls" not in content:
		return content, []
	parser = _ToolDetailsHTMLParser()
	parser.feed(content)
	parser.close()
	return "".join(parser.text_parts).strip(), parser.blocks


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

	def add_error(self, msg: str) -> None:
		if self.errors is None:
			self.errors = []
		self.errors.append(msg)


async def _report_progress(
	progress_callback: ImportProgressCallback | None,
	progress: int,
	stage: str,
) -> None:
	if progress_callback is not None:
		await progress_callback(progress, stage)


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
	return {"imported_from": "open_webui", _OWUI_METADATA_KEY: open_webui}


def _merge_metadata(
	current: dict[str, Any] | None,
	metadata: dict[str, Any],
) -> dict[str, Any]:
	current_metadata = dict(current or {})
	next_metadata = dict(metadata)
	current_open_webui = current_metadata.get(_OWUI_METADATA_KEY)
	next_open_webui = next_metadata.get(_OWUI_METADATA_KEY)
	merged = {**current_metadata, **next_metadata}
	if isinstance(current_open_webui, dict) or isinstance(next_open_webui, dict):
		merged[_OWUI_METADATA_KEY] = {
			**(current_open_webui if isinstance(current_open_webui, dict) else {}),
			**(next_open_webui if isinstance(next_open_webui, dict) else {}),
		}
	return merged


def _owui_metadata_value(metadata: dict[str, Any] | None, key: str) -> Any:
	if metadata is None:
		return None
	open_webui = metadata.get(_OWUI_METADATA_KEY)
	if isinstance(open_webui, dict) and key in open_webui:
		return open_webui.get(key)
	return None


def _owui_origin_filter(metadata_column: Any, deployment: OpenWebUIDeployment) -> Any:
	return metadata_column[_OWUI_METADATA_KEY]["origin"].as_string() == _owui_origin(
		deployment
	)


def _owui_field_filter(metadata_column: Any, key: str, value: str) -> Any:
	return metadata_column[_OWUI_METADATA_KEY][key].as_string() == value


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


@dataclass(slots=True)
class ImportedMessageEntry:
	"""single native message created from one Open WebUI message node."""

	type: MessageType
	content: list[dict[str, Any]] = field(default_factory=list)
	tool_calls: list[dict[str, Any]] = field(default_factory=list)
	tool_call_id: str | None = None
	is_error: bool | None = None
	raw_files: list[dict[str, Any]] = field(default_factory=list)
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolDetailsBlock:
	"""Open WebUI rendered tool call details extracted from assistant HTML."""

	call_id: str
	name: str
	arguments: JSONValue
	output: str
	files: list[dict[str, Any]] = field(default_factory=list)
	is_error: bool = False


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
	except (TypeError, ValueError, OverflowError, OSError):
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


def _extract_messages_map(chat_body: dict[str, Any]) -> dict[str, dict[str, Any]]:
	"""extract Open WebUI messages map keyed by Open WebUI message id."""
	history = chat_body.get("history") or {}
	messages = history.get("messages") if isinstance(history, dict) else None
	if isinstance(messages, dict):
		out: dict[str, dict[str, Any]] = {}
		for key, msg in messages.items():
			if not isinstance(msg, dict):
				continue
			msg_id = msg.get("id") or key
			if not isinstance(msg_id, str):
				continue
			out[msg_id] = msg
		return out

	linear = chat_body.get("messages")
	if isinstance(linear, list):
		out_linear: dict[str, dict[str, Any]] = {}
		prev_id: str | None = None
		for msg in linear:
			if not isinstance(msg, dict):
				continue
			msg_id = msg.get("id")
			if not isinstance(msg_id, str):
				continue
			if "parentId" not in msg and "parent_id" not in msg:
				msg["parentId"] = prev_id
			out_linear[msg_id] = msg
			prev_id = msg_id
		return out_linear
	return {}


def _msg_role_to_type(role: Any) -> MessageType | None:
	if role == "user":
		return MessageType.USER
	if role == "assistant":
		return MessageType.ASSISTANT
	if role == "tool":
		return MessageType.TOOL
	if role == "system":
		return MessageType.SYSTEM
	return None


def _msg_files(msg: dict[str, Any]) -> list[dict[str, Any]]:
	files = msg.get("files")
	if not isinstance(files, list):
		return []
	return [item for item in files if isinstance(item, dict)]


def _message_output_text(item: dict[str, Any]) -> str:
	parts = item.get("content") or item.get("output") or []
	if not isinstance(parts, list):
		return ""
	texts: list[str] = []
	for part in parts:
		if not isinstance(part, dict):
			continue
		text = part.get("text")
		if isinstance(text, str):
			texts.append(text)
	return "".join(texts)


def _tool_output_parts(item: dict[str, Any]) -> list[dict[str, Any]]:
	parts = item.get("output") or item.get("content") or []
	if not isinstance(parts, list):
		return []
	return _content_value_parts(parts)


def _output_item_files(item: dict[str, Any]) -> list[dict[str, Any]]:
	files = item.get("files")
	if isinstance(files, list):
		return [file for file in files if isinstance(file, dict)]
	return []


def _entries_from_output(output: list[Any]) -> list[ImportedMessageEntry]:
	entries: list[ImportedMessageEntry] = []
	pending_content: list[str] = []
	pending_tool_calls: list[dict[str, Any]] = []

	def flush_pending() -> None:
		if not pending_content and not pending_tool_calls:
			return
		text = "".join(pending_content)
		content = [{"type": "text", "text": text}] if text else []
		entries.append(
			ImportedMessageEntry(
				type=MessageType.ASSISTANT,
				content=content,
				tool_calls=list(pending_tool_calls),
			)
		)
		pending_content.clear()
		pending_tool_calls.clear()

	for raw in output:
		if not isinstance(raw, dict):
			continue
		item_type = raw.get("type")
		if item_type == "message":
			text = _message_output_text(raw)
			if text:
				pending_content.append(text)
		elif item_type == "function_call":
			tool_call = _tool_call_from_owui(raw)
			if tool_call:
				pending_tool_calls.append(tool_call)
		elif item_type == "function_call_output":
			flush_pending()
			tool_call_id = _first_str(raw, "call_id", "id") or "owui_tool_call"
			content = _tool_output_parts(raw)
			if not content:
				text = _message_output_text(raw)
				content = [{"type": "text", "text": text}] if text else []
			entries.append(
				ImportedMessageEntry(
					type=MessageType.TOOL,
					content=content,
					tool_call_id=tool_call_id,
					is_error=raw.get("status") == "failed",
					raw_files=_output_item_files(raw),
				)
			)
		elif item_type in ("reasoning", "open_webui:code_interpreter"):
			text = _message_output_text(raw)
			if text:
				pending_content.append(text)

	flush_pending()
	return entries


def _entries_from_html_tool_details(msg: dict[str, Any]) -> list[ImportedMessageEntry]:
	content = msg.get("content")
	if not isinstance(content, str):
		return []
	text, tool_blocks = _parse_tool_details(content)
	if not tool_blocks:
		return []
	tool_calls = [
		{"id": block.call_id, "name": block.name, "arguments": block.arguments}
		for block in tool_blocks
	]
	entries = [
		ImportedMessageEntry(
			type=MessageType.ASSISTANT,
			content=([{"type": "text", "text": text}] if text else []),
			tool_calls=tool_calls,
		)
	]
	for block in tool_blocks:
		entries.append(
			ImportedMessageEntry(
				type=MessageType.TOOL,
				content=(
					[{"type": "text", "text": block.output}] if block.output else []
				),
				tool_call_id=block.call_id,
				is_error=block.is_error,
				raw_files=block.files,
			)
		)
	return entries


def _msg_entries(msg: dict[str, Any]) -> list[ImportedMessageEntry]:
	msg_type = _msg_role_to_type(msg.get("role"))
	if msg_type is None:
		return []

	if msg_type == MessageType.ASSISTANT:
		output = msg.get("output")
		if isinstance(output, list):
			entries = _entries_from_output(output)
			if entries:
				return entries
		entries = _entries_from_html_tool_details(msg)
		if entries:
			return entries

	content = _content_value_parts(msg.get("content"))
	entry = ImportedMessageEntry(
		type=msg_type,
		content=content,
		raw_files=_msg_files(msg),
	)
	if msg_type == MessageType.ASSISTANT:
		tool_calls = msg.get("tool_calls")
		if isinstance(tool_calls, list):
			entry.tool_calls = [
				tool_call
				for raw in tool_calls
				if isinstance(raw, dict)
				if (tool_call := _tool_call_from_owui(raw)) is not None
			]
	elif msg_type == MessageType.TOOL:
		entry.tool_call_id = _first_str(msg, "tool_call_id", "tool_callId")
		entry.is_error = bool(msg.get("is_error", False))
	return [entry]


def _msg_parent_id(msg: dict[str, Any]) -> str | None:
	parent_id = msg.get("parentId")
	if parent_id is None:
		parent_id = msg.get("parent_id")
	if isinstance(parent_id, str) and parent_id:
		return parent_id
	return None


def _topo_sort_owui_messages(
	messages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
	"""order messages so parents come before children."""
	ordered: list[dict[str, Any]] = []
	visited: set[str] = set()

	def visit(msg_id: str) -> None:
		if msg_id in visited:
			return
		msg = messages.get(msg_id)
		if msg is None:
			return
		visited.add(msg_id)
		parent = _msg_parent_id(msg)
		if parent and parent in messages:
			visit(parent)
		ordered.append(msg)

	for msg_id in messages:
		visit(msg_id)
	return ordered


def _folder_id(folder: dict[str, Any]) -> str | None:
	value = folder.get("id")
	return value if isinstance(value, str) and value else None


def _folder_parent_id(folder: dict[str, Any]) -> str | None:
	value = folder.get("parent_id")
	return value if isinstance(value, str) and value else None


def _folder_name(folder: dict[str, Any]) -> str:
	name = folder.get("name")
	if isinstance(name, str) and name.strip():
		return name.strip()
	return "imported folder"


def _folder_path(
	folder: dict[str, Any],
	folders_by_id: dict[str, dict[str, Any]],
) -> str:
	parts: list[str] = []
	seen: set[str] = set()
	current: dict[str, Any] | None = folder
	while current is not None:
		current_id = _folder_id(current)
		if current_id is None or current_id in seen:
			break
		seen.add(current_id)
		parts.append(_folder_name(current))
		parent_id = _folder_parent_id(current)
		current = folders_by_id.get(parent_id) if parent_id is not None else None
	return " / ".join(reversed(parts))


async def _find_folder_project(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	folder_id: str,
) -> Project | None:
	result = await session.scalars(
		select(Project)
		.where(
			Project.owner_id == owner_id,
			Project.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Project.metadata_, deployment),
			_owui_field_filter(Project.metadata_, "folder_id", folder_id),
		)
		.limit(1)
	)
	return result.one_or_none()


async def _find_pinned_chats_project(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
) -> Project | None:
	result = await session.scalars(
		select(Project)
		.where(
			Project.owner_id == owner_id,
			Project.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Project.metadata_, deployment),
			_owui_field_filter(Project.metadata_, "special_project", "pinned_chats"),
		)
		.limit(1)
	)
	return result.one_or_none()


async def _import_folder_projects(
	folders: Iterable[dict[str, Any]],
	session: AsyncSession,
	principal: Principal,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> dict[str, Project]:
	owner_id = TypeID(principal.user.id)
	folders_by_id = {
		folder_id: folder
		for folder in folders
		if (folder_id := _folder_id(folder)) is not None
	}
	projects_by_folder_id: dict[str, Project] = {}
	for folder_id, folder in folders_by_id.items():
		name = _folder_name(folder)
		if not name:
			summary.projects_skipped += 1
			continue
		metadata = _owui_metadata(
			deployment,
			"folder",
			folder_id,
			folder_id=folder_id,
			parent_folder_id=_folder_parent_id(folder),
			folder_path=_folder_path(folder, folders_by_id),
		)
		existing = await _find_folder_project(
			session=session,
			owner_id=owner_id,
			deployment=deployment,
			folder_id=folder_id,
		)
		if existing is not None:
			existing.metadata_ = _merge_metadata(existing.metadata_, metadata)
			projects_by_folder_id[folder_id] = existing
			summary.projects_skipped += 1
			continue
		project = Project(
			name=name[:100],
			description=None,
			owner_id=owner_id,
			metadata_=metadata,
		)
		session.add(project)
		await session.flush()
		created_at = _epoch_to_dt(folder.get("created_at"))
		updated_at = _epoch_to_dt(folder.get("updated_at"))
		if created_at:
			project.created_at = created_at
		if updated_at:
			project.updated_at = updated_at
		projects_by_folder_id[folder_id] = project
		summary.projects_imported += 1
	return projects_by_folder_id


async def _import_pinned_chats_project(
	session: AsyncSession,
	principal: Principal,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> Project:
	owner_id = TypeID(principal.user.id)
	existing = await _find_pinned_chats_project(
		session=session,
		owner_id=owner_id,
		deployment=deployment,
	)
	metadata = _owui_metadata(
		deployment,
		"project",
		"pinned_chats",
		special_project="pinned_chats",
	)
	if existing is not None:
		existing.metadata_ = _merge_metadata(existing.metadata_, metadata)
		summary.projects_skipped += 1
		return existing
	project = Project(
		name=_PINNED_CHATS_PROJECT_NAME,
		description=None,
		owner_id=owner_id,
		metadata_=metadata,
	)
	session.add(project)
	await session.flush()
	summary.projects_imported += 1
	return project


def _chat_folder_id(chat: dict[str, Any]) -> str | None:
	folder_id = chat.get("folder_id")
	if isinstance(folder_id, str) and folder_id:
		return folder_id
	chat_body = chat.get("chat")
	if isinstance(chat_body, dict):
		folder_id = chat_body.get("folder_id")
		if isinstance(folder_id, str) and folder_id:
			return folder_id
		metadata = chat_body.get("metadata") or chat_body.get("meta")
		if isinstance(metadata, dict):
			folder_id = metadata.get("folder_id")
			if isinstance(folder_id, str) and folder_id:
				return folder_id
	return None


def _chat_pinned(chat: dict[str, Any]) -> bool:
	if chat.get("pinned") is True:
		return True
	chat_body = chat.get("chat")
	if isinstance(chat_body, dict) and chat_body.get("pinned") is True:
		return True
	meta = chat.get("meta")
	if isinstance(meta, dict) and meta.get("pinned") is True:
		return True
	return False


def _chat_archived(chat: dict[str, Any]) -> bool:
	if chat.get("archived") is True:
		return True
	chat_body = chat.get("chat")
	if isinstance(chat_body, dict) and chat_body.get("archived") is True:
		return True
	return False


def _chat_id(chat: dict[str, Any]) -> str | None:
	chat_id = _first_str(chat, "id", "chat_id")
	if chat_id:
		return chat_id
	chat_body = chat.get("chat")
	if isinstance(chat_body, dict):
		return _first_str(chat_body, "id", "chat_id")
	return None


def _normalized_placeholder_title(value: str) -> str:
	return " ".join(value.strip().casefold().split())


def _is_owui_placeholder_chat_title(value: str) -> bool:
	return _normalized_placeholder_title(value) in _OWUI_PLACEHOLDER_CHAT_TITLES


def _chat_title(
	chat: dict[str, Any],
	chat_body: dict[str, Any],
) -> tuple[str | None, bool]:
	value = chat.get("title")
	if not isinstance(value, str) or not value.strip():
		value = chat_body.get("title")
	if not isinstance(value, str) or not value.strip():
		return None, True
	title = value.strip()
	if _is_owui_placeholder_chat_title(title):
		return None, True
	return title, False


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


def _chat_tags(chat: dict[str, Any], chat_body: dict[str, Any]) -> list[str]:
	candidates: list[str] = []
	for mapping in (chat, chat_body):
		for key in ("tags", "labels"):
			candidates.extend(_iter_tag_values(mapping.get(key)))
		for meta_key in ("meta", "metadata"):
			meta = mapping.get(meta_key)
			if not isinstance(meta, dict):
				continue
			for key in ("tags", "labels", "tag_ids"):
				candidates.extend(_iter_tag_values(meta.get(key)))

	tags: list[str] = []
	seen: set[str] = set()
	for candidate in candidates:
		tag = _normalize_chat_tag(candidate)
		if tag is None or tag in seen:
			continue
		tags.append(tag)
		seen.add(tag)
	return tags


def _first_model_id(value: Any) -> str | None:
	if isinstance(value, str) and value.strip():
		return value.strip()
	if isinstance(value, list):
		for item in value:
			model_id = _first_model_id(item)
			if model_id is not None:
				return model_id
	return None


def _chat_model_id(chat: dict[str, Any], chat_body: dict[str, Any]) -> str | None:
	for mapping in (chat_body, chat):
		for key in ("model", "model_id", "modelId", "models"):
			model_id = _first_model_id(mapping.get(key))
			if model_id is not None:
				return model_id
		for meta_key in ("meta", "metadata"):
			meta = mapping.get(meta_key)
			if not isinstance(meta, dict):
				continue
			for key in ("model", "model_id", "modelId", "models"):
				model_id = _first_model_id(meta.get(key))
				if model_id is not None:
					return model_id
	return None


def _message_model_id(
	message: dict[str, Any],
	chat_model_id: str | None,
) -> str | None:
	for key in ("model", "model_id", "modelId"):
		model_id = _first_model_id(message.get(key))
		if model_id is not None:
			return model_id
	metadata = message.get("metadata") or message.get("meta")
	if isinstance(metadata, dict):
		for key in ("model", "model_id", "modelId"):
			model_id = _first_model_id(metadata.get(key))
			if model_id is not None:
				return model_id
	return chat_model_id


def _owui_model_name(model: dict[str, Any], model_id: str) -> str:
	name = _first_str(model, "name")
	if name:
		return name
	info = model.get("info")
	if isinstance(info, dict):
		name = _first_str(info, "name")
		if name:
			return name
		meta = info.get("meta")
		if isinstance(meta, dict):
			name = _first_str(meta, "name")
			if name:
				return name
	return model_id


@dataclass
class ModelAgentMatch:
	model_id: str
	model_name: str
	agent_id: TypeID | None


@dataclass
class ModelAgentResolver:
	session: AsyncSession
	client: OpenWebUIClient
	model_names_by_id: dict[str, str] | None = None
	agent_ids_by_name: dict[str, TypeID] | None = None
	resolved_by_id: dict[str, ModelAgentMatch] = field(default_factory=dict)

	async def resolve(self, model_id: str | None) -> ModelAgentMatch | None:
		if model_id is None:
			return None
		cached = self.resolved_by_id.get(model_id)
		if cached is not None:
			return cached
		model_names_by_id = await self._model_names_by_id()
		model_name = model_names_by_id.get(model_id, model_id)
		agent_ids_by_name = await self._agent_ids_by_name()
		match = ModelAgentMatch(
			model_id=model_id,
			model_name=model_name,
			agent_id=agent_ids_by_name.get(model_name),
		)
		self.resolved_by_id[model_id] = match
		return match

	async def _model_names_by_id(self) -> dict[str, str]:
		if self.model_names_by_id is None:
			try:
				models = await self.client.list_models()
			except OpenWebUIError as exc:
				logger.warning("Open WebUI model list unavailable: %s", exc)
				models = []
			self.model_names_by_id = {
				model_id: _owui_model_name(model, model_id)
				for model in models
				if (model_id := _first_str(model, "id")) is not None
			}
		return self.model_names_by_id

	async def _agent_ids_by_name(self) -> dict[str, TypeID]:
		if self.agent_ids_by_name is None:
			rows = await self.session.execute(select(Agent.name, Agent.id))
			self.agent_ids_by_name = {
				name: TypeID(agent_id)
				for name, agent_id in rows.all()
				if isinstance(name, str) and name
			}
		return self.agent_ids_by_name


async def _find_thread_for_chat(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	chat_id: str,
) -> Thread | None:
	result = await session.scalars(
		select(Thread)
		.where(
			Thread.owner_id == owner_id,
			Thread.deleted_at.is_(None),
			Thread.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Thread.metadata_, deployment),
			_owui_field_filter(Thread.metadata_, "chat_id", chat_id),
		)
		.options(selectinload(Thread.projects))
		.limit(1)
	)
	return result.one_or_none()


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


async def _find_note_for_owui_id(
	session: AsyncSession,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	owui_note_id: str,
) -> Note | None:
	result = await session.scalars(
		select(Note)
		.where(
			Note.user_id == owner_id,
			Note.deleted_at.is_(None),
			Note.metadata_["imported_from"].as_string() == "open_webui",
			_owui_origin_filter(Note.metadata_, deployment),
			_owui_field_filter(Note.metadata_, "note_id", owui_note_id),
		)
		.limit(1)
	)
	return result.one_or_none()


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
			create_event=False,
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
	return _file_content_part(
		file_id=TypeID(file.id),
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


async def _load_existing_messages_by_owui_id(
	session: AsyncSession,
	thread_id: TypeID,
) -> tuple[dict[tuple[str, int], Message], dict[str, TypeID]]:
	result = await session.scalars(
		select(Message).where(Message.thread_id == thread_id)
	)
	messages_by_part: dict[tuple[str, int], Message] = {}
	last_by_owui_id: dict[str, TypeID] = {}
	last_part_index_by_owui_id: dict[str, int] = {}
	for message in result.all():
		message_id = _metadata_message_id(message)
		part_index = _metadata_part_index(
			_owui_metadata_value(message.metadata_, "message_part_index")
		)
		if message_id is None or part_index is None:
			continue
		messages_by_part.setdefault((message_id, part_index), message)
		last_part_index = last_part_index_by_owui_id.get(message_id)
		if last_part_index is None or part_index >= last_part_index:
			last_part_index_by_owui_id[message_id] = part_index
			last_by_owui_id[message_id] = TypeID(message.id)
	return messages_by_part, last_by_owui_id


async def _import_one_chat(
	chat: dict[str, Any],
	client: OpenWebUIClient,
	session: AsyncSession,
	principal: Principal,
	deployment: OpenWebUIDeployment,
	projects_by_folder_id: dict[str, Project],
	pinned_project: Project | None,
	model_resolver: ModelAgentResolver,
	summary: ImportSummary,
) -> None:
	owner_id = TypeID(principal.user.id)
	chat_id = _chat_id(chat)
	if chat_id is None:
		summary.chats_skipped += 1
		summary.add_error("chat skipped: missing Open WebUI id")
		return
	folder_id = _chat_folder_id(chat)
	projects: list[Project] = []
	folder_project = projects_by_folder_id.get(folder_id) if folder_id else None
	if folder_project is not None:
		projects.append(folder_project)
	if pinned_project is not None and _chat_pinned(chat):
		projects.append(pinned_project)
	projects = _unique_projects(projects)
	chat_body = chat.get("chat")
	if not isinstance(chat_body, dict):
		summary.chats_skipped += 1
		summary.add_error(f"chat {chat_id} skipped: missing body")
		return

	owui_messages = _extract_messages_map(chat_body)
	if not owui_messages:
		summary.chats_skipped += 1
		return

	title, title_is_placeholder = _chat_title(chat, chat_body)
	tags = _chat_tags(chat, chat_body)
	chat_model_id = _chat_model_id(chat, chat_body)
	thread_metadata = _owui_metadata(
		deployment,
		"chat",
		chat_id,
		chat_id=chat_id,
		folder_id=folder_id,
		pinned=_chat_pinned(chat),
		untitled=title_is_placeholder,
		tags=tags,
	)
	thread = await _find_thread_for_chat(
		session=session,
		owner_id=owner_id,
		deployment=deployment,
		chat_id=chat_id,
	)
	created_thread = thread is None
	if thread is None:
		thread = Thread(
			title=title[:255] if title is not None else None,
			owner_id=owner_id,
			is_archived=_chat_archived(chat),
			tags=tags,
			metadata_=thread_metadata,
			projects=projects,
		)
		session.add(thread)
		await session.flush()
	else:
		thread.title = title[:255] if title is not None else None
		thread.is_archived = _chat_archived(chat)
		if tags or _owui_metadata_value(thread.metadata_, "tags") is not None:
			thread.tags = tags
		thread.metadata_ = _merge_metadata(thread.metadata_, thread_metadata)
		_append_missing_projects_to_thread(thread, projects)

	created_at = _chat_created_at(chat, chat_body)
	updated_at = _chat_updated_at(chat, chat_body, owui_messages)
	participant = await ensure_participant(thread.id, owner_id, session)

	existing_messages, owui_to_typeid = await _load_existing_messages_by_owui_id(
		session, TypeID(thread.id)
	)
	for msg in _topo_sort_owui_messages(owui_messages):
		msg_id = msg.get("id")
		if not isinstance(msg_id, str):
			continue
		model_match = await model_resolver.resolve(
			_message_model_id(msg, chat_model_id)
		)
		entries = _msg_entries(msg)
		if not entries:
			continue

		parent_owui = _msg_parent_id(msg)
		parent_typeid: TypeID | None = (
			owui_to_typeid.get(parent_owui) if parent_owui is not None else None
		)
		last_message_id: TypeID | None = None
		for index, entry in enumerate(entries):
			if (
				entry.type != MessageType.ASSISTANT
				and not entry.content
				and not entry.raw_files
			):
				continue
			metadata = _owui_metadata(
				deployment,
				"message",
				f"{chat_id}:{msg_id}:{index}",
				chat_id=chat_id,
				message_id=msg_id,
				message_part_index=index,
				model_id=model_match.model_id if model_match is not None else None,
				model_name=model_match.model_name if model_match is not None else None,
				agent_id=(
					str(model_match.agent_id)
					if model_match is not None and model_match.agent_id is not None
					else None
				),
			)
			metadata.update(entry.metadata)
			metadata = _merge_metadata(None, metadata)
			existing_message = existing_messages.get((msg_id, index))
			if existing_message is not None:
				existing_message.metadata_ = _merge_metadata(
					existing_message.metadata_, metadata
				)
				if entry.type == MessageType.ASSISTANT and model_match is not None:
					existing_message.sender_agent_id = model_match.agent_id
				await _append_file_parts(
					existing_message,
					entry.raw_files,
					client=client,
					session=session,
					owner_id=owner_id,
					projects=projects,
					deployment=deployment,
					summary=summary,
				)
				last_message_id = TypeID(existing_message.id)
				parent_typeid = last_message_id
				continue
			message = Message(
				thread_id=thread.id,
				parent_id=parent_typeid,
				type=entry.type,
				content=entry.content,
				sender_user_id=(owner_id if entry.type == MessageType.USER else None),
				sender_agent_id=(
					model_match.agent_id
					if entry.type == MessageType.ASSISTANT and model_match is not None
					else None
				),
				tool_call_id=entry.tool_call_id,
				is_error=entry.is_error,
				tool_calls=entry.tool_calls,
				metadata_=metadata,
			)
			session.add(message)
			await session.flush()
			await _append_file_parts(
				message,
				entry.raw_files,
				client=client,
				session=session,
				owner_id=owner_id,
				projects=projects,
				deployment=deployment,
				summary=summary,
			)
			last_message_id = TypeID(message.id)
			parent_typeid = last_message_id

			timestamp = _message_timestamp(msg)
			if timestamp:
				message.created_at = timestamp
				message.updated_at = timestamp

			summary.messages_imported += 1
		if last_message_id is not None:
			owui_to_typeid[msg_id] = last_message_id

	history = chat_body.get("history") or {}
	current_owui_id = history.get("currentId") if isinstance(history, dict) else None
	if isinstance(current_owui_id, str) and current_owui_id in owui_to_typeid:
		thread.current_message_id = owui_to_typeid[current_owui_id]
	elif owui_to_typeid:
		thread.current_message_id = next(reversed(owui_to_typeid.values()))
	if thread.current_message_id is not None:
		participant.last_read_message_id = str(thread.current_message_id)
	if created_at:
		thread.created_at = created_at
	if updated_at:
		thread.updated_at = updated_at
		thread.last_activity_at = updated_at

	if created_thread:
		summary.chats_imported += 1
	else:
		summary.chats_skipped += 1


async def _import_memories(
	memories: Iterable[dict[str, Any]],
	session: AsyncSession,
	principal: Principal,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> None:
	owner_id = TypeID(principal.user.id)
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
		summary.memories_imported += 1


def _note_content(raw: dict[str, Any]) -> str:
	content = raw.get("content")
	if isinstance(content, str):
		return content
	data = raw.get("data")
	if isinstance(data, dict):
		content_data = data.get("content")
		if isinstance(content_data, dict):
			md = content_data.get("md")
			if isinstance(md, str):
				return md
			text = content_data.get("text")
			if isinstance(text, str):
				return text
		md = data.get("md")
		if isinstance(md, str):
			return md
	return ""


def _note_title(raw: dict[str, Any]) -> str:
	title = raw.get("title")
	if isinstance(title, str) and title.strip():
		return title.strip()[:255]
	return "imported note"


def _note_labels(raw: dict[str, Any]) -> list[str]:
	candidates: list[str] = []
	for key in ("labels", "tags"):
		candidates.extend(_iter_tag_values(raw.get(key)))
	for meta_key in ("meta", "metadata"):
		meta = raw.get(meta_key)
		if not isinstance(meta, dict):
			continue
		for key in ("labels", "tags"):
			candidates.extend(_iter_tag_values(meta.get(key)))

	labels: list[str] = []
	seen: set[str] = set()
	for candidate in candidates:
		label = _normalize_chat_tag(candidate)
		if label is None or label in seen:
			continue
		labels.append(label)
		seen.add(label)
	return labels


async def _import_notes(
	notes: Iterable[dict[str, Any]],
	session: AsyncSession,
	principal: Principal,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> None:
	owner_id = TypeID(principal.user.id)
	for raw in notes:
		note_id = _first_str(raw, "id", "note_id")
		if note_id is None:
			summary.notes_skipped += 1
			summary.add_error("note skipped: missing Open WebUI id")
			continue
		metadata = _owui_metadata(
			deployment,
			"note",
			note_id,
			note_id=note_id,
			is_pinned=raw.get("is_pinned") is True,
		)
		created_at = _first_dt(raw, "created_at", "createdAt")
		updated_at = _first_dt(raw, "updated_at", "updatedAt")
		title = _note_title(raw)
		content = _note_content(raw)
		labels = _note_labels(raw)
		existing = await _find_note_for_owui_id(
			session=session,
			owner_id=owner_id,
			deployment=deployment,
			owui_note_id=note_id,
		)
		if existing is not None:
			existing.title = title
			existing.content = content
			existing.labels = labels
			existing.metadata_ = _merge_metadata(existing.metadata_, metadata)
			if created_at:
				existing.created_at = created_at
			if updated_at:
				existing.updated_at = updated_at
			summary.notes_skipped += 1
			continue
		note = Note(
			user_id=owner_id,
			title=title,
			content=content,
			labels=labels,
			metadata_=metadata,
		)
		session.add(note)
		await session.flush()
		if created_at:
			note.created_at = created_at
		if updated_at:
			note.updated_at = updated_at
		summary.notes_imported += 1


def _require_import_permissions(
	principal: Principal,
	include_chats: bool,
	include_memories: bool,
	include_notes: bool,
) -> None:
	if include_chats:
		require_permission(principal, ActionPermission.THREADS_CREATE.value)
		require_permission(principal, ActionPermission.PROJECTS_CREATE.value)
		require_permission(principal, ActionPermission.FILES_CREATE.value)
	if include_memories:
		require_permission(principal, ActionPermission.MEMORIES_CREATE.value)
	if include_notes:
		require_permission(principal, ActionPermission.NOTES_CREATE.value)


async def import_from_open_webui(
	deployment_origin: str,
	credential: str,
	include_chats: bool,
	include_memories: bool,
	session: AsyncSession,
	principal: Principal,
	include_notes: bool = False,
	include_archived_chats: bool = False,
	chat_import_mode: ChatImportMode = "batched",
	progress_callback: ImportProgressCallback | None = None,
) -> ImportSummary:
	"""run a full import from an Open WebUI deployment for the current principal."""
	if not credential or not credential.strip():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Open WebUI credential is required",
		)
	if not (include_chats or include_memories or include_notes):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="select at least one of chats, memories, or notes to import",
		)
	_require_import_permissions(
		principal,
		include_chats=include_chats,
		include_memories=include_memories,
		include_notes=include_notes,
	)

	deployment = get_deployment(deployment_origin)
	origin = normalize_origin(str(deployment.origin))
	summary = ImportSummary(deployment_origin=origin)

	async with OpenWebUIClient(origin=origin, credential=credential) as client:
		if include_chats:
			projects_by_folder_id: dict[str, Project] = {}
			model_resolver = ModelAgentResolver(session=session, client=client)
			await _report_progress(progress_callback, 15, "loading folders")
			try:
				folders = await client.list_folders()
			except OpenWebUIAuthError as exc:
				raise _client_error_to_http_exception(exc) from exc
			except OpenWebUIError as exc:
				summary.add_error(f"folders fetch failed: {exc}")
				folders = []
			await _report_progress(progress_callback, 22, "importing folder projects")
			try:
				projects_by_folder_id = await _import_folder_projects(
					folders,
					session=session,
					principal=principal,
					deployment=deployment,
					summary=summary,
				)
			except Exception as exc:
				await session.rollback()
				logger.exception("failed to import Open WebUI folders")
				summary.add_error(f"folders import failed: {type(exc).__name__}")
				projects_by_folder_id = {}

			pinned_project: Project | None = None

			async def import_loaded_chat(
				index: int,
				total: int,
				chat: dict[str, Any],
				chat_id: str,
			) -> None:
				nonlocal pinned_project
				chat_progress = 40 + int((index - 1) / total * 35)
				if pinned_project is None and _chat_pinned(chat):
					await _report_progress(
						progress_callback,
						chat_progress,
						"importing pinned chats project",
					)
					try:
						async with session.begin_nested():
							pinned_project = await _import_pinned_chats_project(
								session=session,
								principal=principal,
								deployment=deployment,
								summary=summary,
							)
					except Exception as exc:
						logger.exception("failed to import Open WebUI pinned project")
						summary.add_error(
							f"pinned chats project failed: {type(exc).__name__}"
						)
				try:
					await _report_progress(
						progress_callback,
						chat_progress,
						f"importing chat {index}/{total}",
					)
					async with session.begin_nested():
						await _import_one_chat(
							chat,
							client=client,
							session=session,
							principal=principal,
							deployment=deployment,
							projects_by_folder_id=projects_by_folder_id,
							pinned_project=pinned_project,
							model_resolver=model_resolver,
							summary=summary,
						)
				except Exception as exc:
					logger.exception("failed to import Open WebUI chat")
					summary.chats_skipped += 1
					summary.add_error(f"chat {chat_id} failed: {type(exc).__name__}")

			if chat_import_mode == "bulk":
				await _report_progress(
					progress_callback, 30, "loading chats via bulk export"
				)
				try:
					chats = await client.list_bulk_chats(
						include_archived_chats=include_archived_chats
					)
				except OpenWebUIError as exc:
					raise _client_error_to_http_exception(exc) from exc
				total_chats = len(chats)
				await _report_progress(
					progress_callback, 35, f"found {total_chats} chats"
				)
				for index, chat in enumerate(chats, start=1):
					chat_id = _chat_id(chat)
					if chat_id is None:
						summary.chats_skipped += 1
						summary.add_error("chat skipped: missing Open WebUI id")
						continue
					await import_loaded_chat(index, total_chats, chat, chat_id)
			else:
				await _report_progress(progress_callback, 30, "loading chat list")
				try:
					chat_refs = await client.list_chat_refs(
						include_archived_chats=include_archived_chats
					)
				except OpenWebUIError as exc:
					raise _client_error_to_http_exception(exc) from exc
				total_chats = len(chat_refs)
				await _report_progress(
					progress_callback, 35, f"found {total_chats} chats"
				)
				for batch_start in range(0, total_chats, _CHAT_FETCH_BATCH_SIZE):
					batch_refs = chat_refs[
						batch_start : batch_start + _CHAT_FETCH_BATCH_SIZE
					]
					batch_start_index = batch_start + 1
					batch_end_index = batch_start + len(batch_refs)
					batch_progress = 40 + int(batch_start / total_chats * 35)
					await _report_progress(
						progress_callback,
						batch_progress,
						(
							"loading chats "
							f"{batch_start_index}-{batch_end_index}/{total_chats}"
						),
					)
					batch_items: list[tuple[int, dict[str, Any], str]] = []
					for offset, chat_ref in enumerate(batch_refs):
						chat_id = _first_str(chat_ref, "id", "chat_id")
						if chat_id is None:
							summary.chats_skipped += 1
							summary.add_error("chat skipped: missing Open WebUI id")
							continue
						batch_items.append(
							(batch_start + offset + 1, chat_ref, chat_id)
						)
					if not batch_items:
						continue
					fetch_results = await asyncio.gather(
						*(client.get_chat(chat_id) for _, _, chat_id in batch_items),
						return_exceptions=True,
					)
					for (index, chat_ref, chat_id), fetch_result in zip(
						batch_items, fetch_results, strict=True
					):
						if isinstance(fetch_result, OpenWebUIAuthError):
							raise _client_error_to_http_exception(
								fetch_result
							) from fetch_result
						if isinstance(fetch_result, asyncio.CancelledError):
							raise fetch_result
						if isinstance(fetch_result, OpenWebUIError):
							summary.chats_skipped += 1
							summary.add_error(
								f"chat {chat_id} fetch failed: {fetch_result}"
							)
							continue
						if isinstance(fetch_result, BaseException):
							summary.chats_skipped += 1
							error_type = type(fetch_result).__name__
							summary.add_error(
								f"chat {chat_id} fetch failed: {error_type}"
							)
							continue
						chat_body = fetch_result
						if chat_body is None:
							summary.chats_skipped += 1
							summary.add_error(f"chat {chat_id} skipped: empty response")
							continue
						chat = {**chat_ref, **chat_body}
						if chat_ref.get("archived") is True:
							chat["archived"] = True
						await import_loaded_chat(index, total_chats, chat, chat_id)
			await _report_progress(progress_callback, 78, "chats imported")

		if include_memories:
			await _report_progress(progress_callback, 82, "loading memories")
			try:
				memories = await client.list_memories()
			except OpenWebUIAuthError as exc:
				raise _client_error_to_http_exception(exc) from exc
			except OpenWebUIError as exc:
				summary.add_error(f"memories fetch failed: {exc}")
				memories = []
			await _report_progress(progress_callback, 86, "importing memories")
			try:
				await _import_memories(
					memories,
					session=session,
					principal=principal,
					deployment=deployment,
					summary=summary,
				)
			except Exception as exc:
				await session.rollback()
				logger.exception("failed to import Open WebUI memories")
				summary.add_error(f"memories import failed: {type(exc).__name__}")
			await _report_progress(progress_callback, 88, "memories imported")

		if include_notes:
			await _report_progress(progress_callback, 89, "loading notes")
			try:
				notes = await client.list_notes()
			except OpenWebUIAuthError as exc:
				raise _client_error_to_http_exception(exc) from exc
			except OpenWebUIError as exc:
				summary.add_error(f"notes fetch failed: {exc}")
				notes = []
			await _report_progress(progress_callback, 91, "importing notes")
			try:
				await _import_notes(
					notes,
					session=session,
					principal=principal,
					deployment=deployment,
					summary=summary,
				)
			except Exception as exc:
				await session.rollback()
				logger.exception("failed to import Open WebUI notes")
				summary.add_error(f"notes import failed: {type(exc).__name__}")
			await _report_progress(progress_callback, 93, "notes imported")

	await session.commit()
	await _report_progress(progress_callback, 95 if include_notes else 90, "finalizing")
	return summary
