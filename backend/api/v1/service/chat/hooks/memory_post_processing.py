"""memory post-processing hook - enqueue durable memory maintenance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.database import async_session_local
from api.schemas.preferences import AIPreferences
from api.settings import settings as app_settings
from api.v1.service.chat.hooks.base import Hook
from api.v1.service.chat.message_metadata import get_message_id
from api.v1.service.chat.run_status import run_status_store
from api.v1.tasks.threads import (
	start_memory_post_processing_task,
)
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import AssistantMessage, UserMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

logger = logging.getLogger(__name__)


def _latest_context_message_id(thread: SDKThread) -> str | None:
	"""return the latest persisted non-system message id in the thread."""
	for message in reversed(thread.messages):
		if isinstance(message, SDKSystemMessage):
			continue
		message_id = get_message_id(message)
		if message_id:
			return message_id
	return None


def _recent_turn_snapshot(thread: SDKThread, k: int) -> str:
	"""build a role-annotated, negative-indexed snapshot of recent turns.

	a turn is a contiguous block of user or assistant messages. the most
	recent turn is labeled -1, the one before it -2, and so on.
	"""
	turns: list[tuple[str, str]] = []
	current_role: str | None = None
	current_texts: list[str] = []
	for msg in thread.messages:
		if not isinstance(msg, (UserMessage, AssistantMessage)):
			continue
		role = msg.role
		if role != current_role:
			if current_texts:
				turns.append((current_role or "", "\n".join(current_texts)))
			current_role = role
			current_texts = []
		text = msg.text
		if text:
			current_texts.append(text)
	if current_texts:
		turns.append((current_role or "", "\n".join(current_texts)))

	recent = turns[-k:] if k < len(turns) else turns
	total = len(recent)
	lines = [
		f"{offset - total}. {role}: {text}"
		for offset, (role, text) in enumerate(recent)
	]
	return "\n".join(lines)


async def _is_final_assistant_iteration(
	thread: SDKThread,
	app_context: AppContext,
) -> bool:
	if not thread.messages:
		return False
	last_message = thread.messages[-1]
	if not isinstance(last_message, AssistantMessage) or last_message.tool_calls:
		return False
	if app_context.run_id is None:
		return True
	return not await run_status_store.has_in_flight_steering(app_context.run_id)


class MemoryPostProcessingHook(Hook):
	"""post-execution hook that maintains memory quality.

	analyzes the completed conversation thread and existing memories
	to detect stale, duplicate, or conflicting entries. schedules
	post-processing as a background task to avoid blocking the response.
	"""

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
		_ = agent_context
		if app_context is None:
			return
		thread = state.thread
		if not await _is_final_assistant_iteration(thread, app_context):
			return

		# gate on user preference - skip when memories disabled.
		ai = app_context.principal.user.prefs.ai
		if isinstance(ai, AIPreferences) and ai.memories_enabled is False:
			logger.debug("memory post-processing skipped: disabled by user")
			return

		user_id = app_context.user_id
		if user_id is None:
			return

		# only process if there are user messages in the thread
		user_messages = [m for m in thread.messages if m.role == "user"]
		if not user_messages:
			return

		query_text = app_context.retrieval.query_text
		if query_text is None:
			query_text = "\n".join(thread.recent_turns(app_settings.ai.retrieval_turns))
		if not query_text.strip():
			return

		conversation_snapshot = _recent_turn_snapshot(
			thread,
			app_settings.ai.memory.post_processing_turns,
		)
		anchor_message_id = _latest_context_message_id(thread)
		thread_id = (
			str(app_context.thread_id) if app_context.thread_id is not None else None
		)
		run_id = str(app_context.run_id) if app_context.run_id is not None else None

		try:
			async with async_session_local() as task_session:
				await start_memory_post_processing_task(
					task_session,
					app_context.principal,
					query_text=query_text,
					max_related_memories=self.max_related_memories,
					conversation_snapshot=conversation_snapshot or None,
					thread_id=thread_id,
					message_id=anchor_message_id,
					run_id=run_id,
					emit_activity=True,
				)
		except Exception:
			logger.exception("failed to enqueue memory post-processing task")
