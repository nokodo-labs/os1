"""memory context filter - injects relevant memories into the system prompt."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import Field

from api.models.memory import Memory
from api.settings import settings as app_settings
from api.v1.service.chat.filters.base import Filter
from api.v1.service.memories import query_relevant_memories
from api.v1.service.prompt_runtime import SENTINEL_USER_MEMORIES
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


class MemoryContextFilter(Filter):
	"""pre-filter that injects relevant memories into the system prompt.

	uses hybrid (dense + BM25) vector search against recent user messages
	to retrieve contextually relevant memories.

	respects app_settings.ai.memory for top_k, messages_to_consider,
	and similarity_threshold.

	only activates when the admin includes {{ user_memories }} in the
	agent's system prompt. if the variable is absent, the filter is a no-op.
	"""

	name: str = Field(default="memory_context")
	description: str = Field(default="injects relevant memories into the system prompt")

	async def process(
		self,
		thread: SDKThread,
		app_context: AppContext | None,
	) -> SDKThread:
		if app_context is None:
			raise ValueError("AppContext is required for MemoryContextFilter")

		# locate system message and check for the injection sentinel.
		# if the admin didn't include {{ user_memories }}, skip entirely.
		system_idx = next(
			(i for i, m in enumerate(thread.messages) if m.role == "system"),
			None,
		)
		if system_idx is None:
			return thread

		existing = thread.messages[system_idx]
		if not isinstance(existing, SDKSystemMessage) or not existing.text:
			return thread

		system_text = existing.text
		if SENTINEL_USER_MEMORIES not in system_text:
			return thread

		mem_cfg = app_settings.ai.memory

		# build query from the N most recent user messages.
		user_texts = [
			m.text
			for m in reversed(thread.messages)
			if m.role == "user" and getattr(m, "text", None)
		][: mem_cfg.messages_to_consider]

		if not user_texts:
			# no user message yet - clear the sentinel and return.
			thread.messages[system_idx] = SDKSystemMessage.from_text(
				system_text.replace(SENTINEL_USER_MEMORIES, "")
			)
			return thread

		query = "\n".join(reversed(user_texts))

		memories = await query_relevant_memories(
			query,
			app_context.session,
			principal=app_context.principal,
			limit=mem_cfg.top_k,
			score_threshold=mem_cfg.similarity_threshold,
		)
		content = self._format_memories(memories) if memories else ""

		thread.messages[system_idx] = SDKSystemMessage.from_text(
			system_text.replace(SENTINEL_USER_MEMORIES, content)
		)
		return thread

	def _format_memories(self, memories: list[Memory]) -> str:
		entries = []
		for mem in memories:
			entry: dict = {"content": mem.content}
			if mem.category:
				entry["category"] = mem.category
			if mem.created_at:
				entry["created_at"] = mem.created_at.isoformat()
			if mem.updated_at:
				entry["updated_at"] = mem.updated_at.isoformat()
			entries.append(entry)
		memories_json = json.dumps(entries, indent=2, ensure_ascii=False)
		return f"<long_term_memory>\n{memories_json}\n</long_term_memory>"
