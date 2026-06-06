"""Open WebUI chat parsing and import writers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.agent import Agent
from api.models.message import Message, MessageType
from api.models.project import Project
from api.models.thread import Thread
from api.open_webui import OpenWebUIClient, OpenWebUIError
from api.settings import OpenWebUIDeployment
from api.v1.service.integrations.open_webui.common import (
	ImportSummary,
	_append_missing_projects_to_thread,
	_chat_created_at,
	_chat_updated_at,
	_first_str,
	_iter_tag_values,
	_merge_metadata,
	_message_timestamp,
	_metadata_message_id,
	_metadata_part_index,
	_normalize_chat_tag,
	_owui_field_filter,
	_owui_metadata,
	_owui_metadata_value,
	_owui_origin_filter,
	_unique_projects,
)
from api.v1.service.integrations.open_webui.files import (
	_append_file_parts,
	_file_entry_id,
)
from api.v1.service.integrations.open_webui.messages import (
	_extract_messages_map,
	_msg_entries,
	_msg_parent_id,
	_topo_sort_owui_messages,
)
from api.v1.service.threads import ensure_participant
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


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


def _chat_owui_file_ids(chat: dict[str, Any]) -> list[str]:
	"""collect the Open WebUI file ids a chat references, sorted and deduped."""
	chat_body = chat.get("chat")
	if not isinstance(chat_body, dict):
		return []
	owui_messages = _extract_messages_map(chat_body)
	if not owui_messages:
		return []
	file_ids: set[str] = set()
	for msg in owui_messages.values():
		for entry in _msg_entries(msg):
			for raw_file in entry.raw_files:
				file_id = _file_entry_id(raw_file)
				if file_id:
					file_ids.add(file_id)
	return sorted(file_ids)


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

	async def prewarm(self) -> None:
		"""populate both caches so resolve() is a pure lookup under fan-out."""
		await self._model_names_by_id()
		await self._agent_ids_by_name()

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
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	projects_by_folder_id: dict[str, Project],
	pinned_project: Project | None,
	model_resolver: ModelAgentResolver,
	summary: ImportSummary,
) -> None:
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
		summary.thread_ids.append(thread.id)
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
