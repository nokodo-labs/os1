"""memory context filter - injects relevant memories into the system prompt."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.models.memory import Memory
from api.settings import settings as app_settings
from api.v1.service.chat.filters.base import Filter
from api.v1.service.memories import query_relevant_memories
from api.v1.service.prompt_runtime import SENTINEL_USER_MEMORIES
from nokodo_ai.context import AgentContext
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


logger = logging.getLogger(__name__)


class MemoryContextFilter(Filter):
	"""pre-filter that injects relevant memories into the system prompt.

	uses hybrid (dense + BM25) vector search against the pre-computed
	retrieval context to retrieve contextually relevant memories.

	respects app_settings.ai.memory for top_k and similarity_threshold.
	the retrieval query and embedding are built explicitly in agents.py
	before filters run; this filter only reads from them.

	only activates when the admin includes {{ user_memories }} in the
	agent's system prompt. if the variable is absent, the filter is a no-op.
	"""

	name: str = Field(default="memory_context")
	description: str = Field(default="injects relevant memories into the system prompt")

	async def process(
		self,
		thread: SDKThread,
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> SDKThread:
		_ = agent_context
		if app_context is None:
			raise ValueError("AppContext is required for MemoryContextFilter")

		# locate system message and check for the injection sentinel.
		# if the admin didn't include {{ user_memories }}, skip entirely.
		system_msg = thread.system_message
		if system_msg is None:
			return thread

		system_text = system_msg.text
		if not system_text or SENTINEL_USER_MEMORIES not in system_text:
			return thread

		mem_cfg = app_settings.ai.memory
		retrieval = app_context.retrieval

		query_text = retrieval.query_text
		if query_text is None:
			# retrieval_pre_build is off or thread has no turns yet; try to
			# build the query here, or clear the sentinel and bail.
			_turns = thread.recent_turns(app_settings.ai.retrieval_turns)
			if not _turns:
				self._replace_sentinel(thread, SENTINEL_USER_MEMORIES, "")
				return thread
			query_text = "\n".join(_turns)

		memories = await query_relevant_memories(
			query_text,
			app_context.session,
			principal=app_context.principal,
			limit=mem_cfg.top_k,
			score_threshold=mem_cfg.similarity_threshold,
			query_embedding=retrieval.query_embedding,
		)
		content = self._format_memories(memories) if memories else ""

		self._replace_sentinel(thread, SENTINEL_USER_MEMORIES, content)
		return thread

	def _format_memories(self, memories: list[Memory]) -> str:
		entries = []
		for mem in memories:
			entry: dict = {"content": mem.content}
			if mem.tags:
				entry["tags"] = mem.tags
			if mem.created_at:
				entry["created_at"] = mem.created_at.isoformat()
			if mem.updated_at:
				entry["updated_at"] = mem.updated_at.isoformat()
			entries.append(entry)
		memories_json = json.dumps(entries, indent=2, ensure_ascii=False)
		return memories_json
