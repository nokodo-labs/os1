"""Open WebUI import service."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.memory import Memory
from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.open_webui import OpenWebUIAuthError, OpenWebUIClient, OpenWebUIError
from api.permissions import ActionPermission
from api.settings import OpenWebUIDeployment
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.integrations.open_webui.deployments import (
	get_deployment,
	normalize_origin,
)
from api.v1.service.threads import ensure_participant
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ImportSummary:
	"""result of an Open WebUI import run."""

	deployment_origin: str
	chats_imported: int = 0
	chats_skipped: int = 0
	messages_imported: int = 0
	memories_imported: int = 0
	memories_skipped: int = 0
	errors: list[str] | None = None

	def add_error(self, msg: str) -> None:
		if self.errors is None:
			self.errors = []
		self.errors.append(msg)


def _epoch_to_dt(value: Any) -> datetime | None:
	"""coerce an Open WebUI epoch value to a UTC datetime."""
	if value in (None, 0, "0"):
		return None
	try:
		return datetime.fromtimestamp(int(value), tz=UTC)
	except (TypeError, ValueError, OverflowError, OSError):
		return None


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
	if role == "system":
		return MessageType.SYSTEM
	return None


def _msg_content_parts(msg: dict[str, Any]) -> list[dict[str, Any]]:
	"""convert an Open WebUI message body to our content parts list."""
	parts: list[dict[str, Any]] = []
	content = msg.get("content")
	if isinstance(content, str) and content.strip():
		parts.append({"type": "text", "text": content})
	elif isinstance(content, list):
		for block in content:
			if isinstance(block, dict):
				text = block.get("text") if isinstance(block.get("text"), str) else None
				if text:
					parts.append({"type": "text", "text": text})

	files = msg.get("files")
	if isinstance(files, list):
		for file_entry in files:
			if not isinstance(file_entry, dict):
				continue
			file_obj = file_entry.get("file")
			url = file_entry.get("url")
			if url is None and isinstance(file_obj, dict):
				url = file_obj.get("url")
			if not isinstance(url, str):
				continue
			media_type = (
				file_entry.get("type")
				if isinstance(file_entry.get("type"), str)
				else None
			)
			filename = (
				file_entry.get("name")
				if isinstance(file_entry.get("name"), str)
				else None
			)
			kind = "image" if (media_type or "").startswith("image") else "file"
			parts.append(
				{
					"type": kind,
					"url": url,
					"filename": filename,
					"media_type": media_type,
				}
			)
	return parts


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


async def _import_one_chat(
	chat: dict[str, Any],
	session: AsyncSession,
	principal: Principal,
	deployment: OpenWebUIDeployment,
	summary: ImportSummary,
) -> None:
	owner_id = TypeID(principal.user.id)
	chat_body = chat.get("chat")
	if not isinstance(chat_body, dict):
		summary.chats_skipped += 1
		summary.add_error(f"chat {chat.get('id')!s} skipped: missing body")
		return

	owui_messages = _extract_messages_map(chat_body)
	if not owui_messages:
		summary.chats_skipped += 1
		return

	title = chat.get("title") or chat_body.get("title") or "imported chat"
	if not isinstance(title, str):
		title = str(title)

	thread = Thread(
		title=title[:255],
		owner_id=owner_id,
		is_archived=bool(chat.get("archived", False)),
		tags=[],
		metadata_={
			"imported_from": "open_webui",
			"owui_origin": str(deployment.origin),
			"owui_chat_id": chat.get("id"),
		},
	)
	session.add(thread)
	await session.flush()

	created_at = _epoch_to_dt(chat.get("created_at"))
	updated_at = _epoch_to_dt(chat.get("updated_at"))
	if created_at:
		thread.created_at = created_at
	if updated_at:
		thread.updated_at = updated_at
		thread.last_activity_at = updated_at

	await ensure_participant(thread.id, owner_id, session)

	owui_to_typeid: dict[str, TypeID] = {}
	for msg in _topo_sort_owui_messages(owui_messages):
		msg_id = msg.get("id")
		if not isinstance(msg_id, str):
			continue
		msg_type = _msg_role_to_type(msg.get("role"))
		if msg_type is None:
			continue
		parts = _msg_content_parts(msg)
		if not parts and msg_type != MessageType.ASSISTANT:
			continue

		parent_owui = _msg_parent_id(msg)
		parent_typeid = (
			owui_to_typeid.get(parent_owui) if parent_owui is not None else None
		)

		message = Message(
			thread_id=thread.id,
			parent_id=parent_typeid,
			type=msg_type,
			content=parts,
			sender_user_id=(owner_id if msg_type == MessageType.USER else None),
			metadata_={
				"imported_from": "open_webui",
				"owui_message_id": msg_id,
				"owui_model": msg.get("model"),
			},
		)
		session.add(message)
		await session.flush()
		owui_to_typeid[msg_id] = TypeID(message.id)

		timestamp = _epoch_to_dt(msg.get("timestamp"))
		if timestamp:
			message.created_at = timestamp
			message.updated_at = timestamp

		summary.messages_imported += 1

	history = chat_body.get("history") or {}
	current_owui_id = history.get("currentId") if isinstance(history, dict) else None
	if isinstance(current_owui_id, str) and current_owui_id in owui_to_typeid:
		thread.current_message_id = owui_to_typeid[current_owui_id]
	elif owui_to_typeid:
		thread.current_message_id = next(reversed(owui_to_typeid.values()))

	summary.chats_imported += 1


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
		memory = Memory(
			user_id=owner_id,
			content=content,
			metadata_={
				"imported_from": "open_webui",
				"owui_origin": str(deployment.origin),
				"owui_memory_id": raw.get("id"),
			},
		)
		session.add(memory)
		await session.flush()
		created_at = _epoch_to_dt(raw.get("created_at"))
		updated_at = _epoch_to_dt(raw.get("updated_at"))
		if created_at:
			memory.created_at = created_at
		if updated_at:
			memory.updated_at = updated_at
		summary.memories_imported += 1


def _require_import_permissions(
	principal: Principal,
	include_chats: bool,
	include_memories: bool,
) -> None:
	if include_chats:
		require_permission(principal, ActionPermission.THREADS_CREATE.value)
	if include_memories:
		require_permission(principal, ActionPermission.MEMORIES_CREATE.value)


async def import_from_open_webui(
	deployment_origin: str,
	credential: str,
	include_chats: bool,
	include_memories: bool,
	session: AsyncSession,
	principal: Principal,
) -> ImportSummary:
	"""run a full import from an Open WebUI deployment for the current principal."""
	if not credential or not credential.strip():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Open WebUI credential is required",
		)
	if not (include_chats or include_memories):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="select at least one of chats or memories to import",
		)
	_require_import_permissions(
		principal,
		include_chats=include_chats,
		include_memories=include_memories,
	)

	deployment = get_deployment(deployment_origin)
	origin = normalize_origin(str(deployment.origin))
	summary = ImportSummary(deployment_origin=origin)

	async with OpenWebUIClient(origin=origin, credential=credential) as client:
		if include_chats:
			try:
				chats = await client.list_all_chats()
			except OpenWebUIError as exc:
				raise _client_error_to_http_exception(exc) from exc
			for chat in chats:
				try:
					await _import_one_chat(
						chat,
						session=session,
						principal=principal,
						deployment=deployment,
						summary=summary,
					)
				except Exception as exc:
					await session.rollback()
					logger.exception("failed to import Open WebUI chat")
					summary.chats_skipped += 1
					summary.add_error(
						f"chat {chat.get('id')!s} failed: {type(exc).__name__}"
					)

		if include_memories:
			try:
				memories = await client.list_memories()
			except OpenWebUIAuthError as exc:
				raise _client_error_to_http_exception(exc) from exc
			except OpenWebUIError as exc:
				summary.add_error(f"memories fetch failed: {exc}")
				memories = []
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

	await session.commit()
	return summary
