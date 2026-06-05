"""memory post-processing scheduler helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.database import async_session_local
from api.schemas.preferences import AIPreferences
from api.settings import settings as app_settings
from api.v1.service.chat.hooks.base import Hook
from api.v1.service.chat.run_status import run_status_store
from api.v1.tasks.threads import start_memory_post_processing_task
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	TextContent,
	UserMessage,
)
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

logger = logging.getLogger(__name__)

_ATTACHMENT_SKIP_METADATA_KEYS = frozenset({"base64", "data", "url"})
_ATTACHMENT_PRIORITY_METADATA_KEYS = (
	"file_id",
	"name",
	"filename",
	"title",
	"description",
	"summary",
	"media_type",
	"mime_type",
	"updated_at",
)


def _metadata_snapshot_value(value: object) -> str | None:
	"""return a compact scalar metadata value safe for memory snapshots."""
	if value is None:
		return None
	if isinstance(value, str):
		cleaned = " ".join(value.split())
		return cleaned or None
	if isinstance(value, (int, float, bool)):
		return str(value)
	return None


def _format_attachment_snapshot(part: FileContent | ImageContent) -> str | None:
	"""format only attachment metadata, never raw file payloads."""
	items: list[tuple[str, str]] = []
	seen_keys: set[str] = set()

	def append_value(key: str, value: object) -> None:
		key = str(key)
		if key.startswith("_") or key in _ATTACHMENT_SKIP_METADATA_KEYS:
			return
		text = _metadata_snapshot_value(value)
		if text is None:
			return
		items.append((key, text))
		seen_keys.add(key)

	append_value("name", part.filename)
	append_value("media_type", part.media_type)
	metadata = part.metadata or {}
	for key in _ATTACHMENT_PRIORITY_METADATA_KEYS:
		if key not in metadata or key in seen_keys:
			continue
		append_value(key, metadata[key])
	for raw_key, raw_value in metadata.items():
		key = str(raw_key)
		if key in seen_keys:
			continue
		append_value(key, raw_value)

	if not items:
		return None
	return "attachment: " + "; ".join(f"{key}={value}" for key, value in items)


def _message_snapshot_parts(message: UserMessage | AssistantMessage) -> list[str]:
	"""extract text and attachment metadata from a user or assistant message."""
	parts: list[str] = []
	for part in message.content:
		if isinstance(part, TextContent):
			text = part.text.strip()
			if text:
				parts.append(text)
		elif isinstance(part, (FileContent, ImageContent)):
			attachment = _format_attachment_snapshot(part)
			if attachment:
				parts.append(attachment)
	return parts


def _recent_turn_snapshot(thread: SDKThread, k: int) -> str | None:
	"""build a role snapshot with no tool messages or tool call dumps."""
	turns: list[tuple[str, str]] = []
	current_role: str | None = None
	current_parts: list[str] = []

	for msg in thread.messages:
		if not isinstance(msg, (UserMessage, AssistantMessage)):
			continue
		parts = _message_snapshot_parts(msg)
		if not parts:
			continue
		role = msg.role
		if role != current_role:
			if current_parts:
				turns.append((current_role or "", "\n".join(current_parts)))
			current_role = role
			current_parts = []
		current_parts.extend(parts)

	if current_parts:
		turns.append((current_role or "", "\n".join(current_parts)))

	if not turns:
		return None
	recent = turns[-k:] if k < len(turns) else turns
	total = len(recent)
	lines = [
		f"{offset - total}. {role}: {text}"
		for offset, (role, text) in enumerate(recent)
	]
	return "\n".join(lines)


async def schedule_memory_post_processing(
	thread: SDKThread,
	app_context: AppContext | None,
	message_id: str | TypeID | None = None,
	message_ref: str | None = None,
	max_related_memories: int = 10,
	emit_activity: bool = True,
) -> None:
	"""schedule memory maintenance anchored to the completed assistant turn."""
	if app_context is None:
		return
	if not app_settings.ai.memory.enable_memory:
		return
	if app_context.thread_id is None:
		return
	if message_id is None and message_ref is None:
		return
	if app_context.run_id is not None:
		if await run_status_store.has_in_flight_steering(app_context.run_id):
			return

	# gate on user preference - skip when memories disabled.
	ai = app_context.principal.user.prefs.ai
	if isinstance(ai, AIPreferences) and ai.memories_enabled is False:
		logger.debug("memory post-processing skipped: disabled by user")
		return

	if not any(isinstance(message, UserMessage) for message in thread.messages):
		return

	conversation_snapshot = _recent_turn_snapshot(
		thread,
		app_settings.ai.memory.post_processing_turns,
	)
	if not conversation_snapshot:
		return
	query_text = app_context.retrieval.query_text
	if query_text is None or not query_text.strip():
		query_text = conversation_snapshot

	thread_id = str(app_context.thread_id)
	run_id = str(app_context.run_id) if app_context.run_id is not None else None
	try:
		async with async_session_local() as task_session:
			await start_memory_post_processing_task(
				task_session,
				app_context.principal,
				query_text=query_text,
				max_related_memories=max_related_memories,
				conversation_snapshot=conversation_snapshot,
				thread_id=thread_id,
				message_id=str(message_id) if message_id is not None else None,
				message_ref=message_ref,
				run_id=run_id,
				emit_activity=emit_activity,
			)
	except Exception:
		logger.exception("failed to enqueue memory post-processing task")


class MemoryPostProcessingHook(Hook):
	"""registered hook marker for memory post-processing."""

	name: str = Field(default="memory_post_processing")
	description: str = Field(
		default=(
			"maintains memory quality by deduplicating, "
			"updating, and deleting stale entries"
		),
	)
	max_related_memories: int = Field(default=10, exclude=True)

	async def execute(
		self,
		state: AgentIterationSnapshot[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> None:
		"""schedule memory processing only after the SDK run is semantically final."""
		_ = agent_context
		if not state.final:
			return
		if app_context is None:
			return
		await schedule_memory_post_processing(
			state.thread,
			app_context,
			message_ref=app_context.final_assistant_message_ref,
			max_related_memories=self.max_related_memories,
			emit_activity=True,
		)
