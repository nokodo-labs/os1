"""parsing helpers for Open WebUI chat message content and tool calls."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from api.models.message import MessageType
from api.v1.service.integrations.open_webui.common import (
	OWUI_METADATA_KEY,
	_coerce_json_value,
	_first_str,
	_json_attr,
	_looks_like_image,
)
from nokodo_ai.types.json import JSONValue
from nokodo_ai.utils.typeid import TypeID


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


def _file_content_part(
	file_id: TypeID | None,
	url: str | None,
	filename: str | None,
	media_type: str | None,
	owui_file_id: str | None,
	checksum_sha256: str | None = None,
) -> dict[str, Any] | None:
	if file_id is None and not url:
		return None
	metadata: dict[str, Any] = {
		"imported_from": "open_webui",
		"attachment_status": "active",
	}
	if file_id is not None:
		metadata["file_id"] = str(file_id)
	if checksum_sha256 is not None:
		metadata["checksum_sha256"] = checksum_sha256
	if owui_file_id is not None:
		metadata[OWUI_METADATA_KEY] = {"file_id": owui_file_id}
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
