"""memory post-processing scheduler helpers."""

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.database import async_session_local
from api.schemas.preferences import AIPreferences
from api.settings import settings as app_settings
from api.v1.service.chat.hooks.base import Hook
from api.v1.service.memories import start_memory_post_processing_task
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


def _format_tool_cluster(tool_names: list[str]) -> str | None:
	"""summarize a cluster of tool calls as a compact synthetic line.

	shows names with per-name counts for up to 3 distinct tools, otherwise just
	the total number of calls. never exposes tool arguments or outputs.
	"""
	if not tool_names:
		return None
	if len(tool_names) == 1:
		return f"[called {tool_names[0]} tool]"
	counts: dict[str, int] = {}
	for name in tool_names:
		counts[name] = counts.get(name, 0) + 1
	if len(counts) <= 3:
		parts = [
			f"{name} tool {count} times" if count > 1 else f"{name} tool once"
			for name, count in counts.items()
		]
		return f"[called {', '.join(parts)}]"
	return f"[called {len(tool_names)} tools]"


def _recent_turn_snapshot(thread: SDKThread, k: int) -> str | None:
	"""build a role snapshot preserving chronological order within each turn.

	text and tool-cluster summaries appear in the order they occurred; a run of
	consecutive tool calls collapses to one synthetic line at its position. tool
	messages and tool call arguments/outputs never appear.
	"""
	turns: list[tuple[str, str]] = []
	current_role: str | None = None
	ordered_parts: list[str] = []
	pending_tools: list[str] = []

	def flush_tools() -> None:
		nonlocal pending_tools
		cluster = _format_tool_cluster(pending_tools)
		if cluster:
			ordered_parts.append(cluster)
		pending_tools = []

	def flush_turn() -> None:
		nonlocal ordered_parts, pending_tools
		flush_tools()
		if ordered_parts:
			turns.append((current_role or "", "\n".join(ordered_parts)))
		ordered_parts = []
		pending_tools = []

	for msg in thread.messages:
		if not isinstance(msg, (UserMessage, AssistantMessage)):
			continue
		role = msg.role
		if role != current_role:
			flush_turn()
			current_role = role
		for part in _message_snapshot_parts(msg):
			flush_tools()
			ordered_parts.append(part)
		if isinstance(msg, AssistantMessage) and msg.tool_calls:
			pending_tools.extend(tc.name for tc in msg.tool_calls)

	flush_turn()

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
	if (
		app_context.has_in_flight_input is not None
		and await app_context.has_in_flight_input()
	):
		return

	# gate on user preference - skip when memories disabled.
	ai = app_context.principal.subject.prefs.ai
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

	async def run(
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
