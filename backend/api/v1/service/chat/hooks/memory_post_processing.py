"""memory post-processing hook - enqueue durable memory maintenance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.database import async_session_local
from api.settings import settings as app_settings
from api.v1.service.chat.hooks.base import Hook
from api.v1.tasks.threads import (
	start_memory_post_processing_task,
)
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

logger = logging.getLogger(__name__)


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
		thread: SDKThread,
		app_context: AppContext | None,
	) -> None:
		if app_context is None:
			return

		# gate on user preference - skip when memories disabled.
		ai = app_context.principal.user.prefs.ai
		if ai is not None and ai.memories_enabled is False:
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

		try:
			async with async_session_local() as task_session:
				await start_memory_post_processing_task(
					task_session,
					app_context.principal,
					query_text=query_text,
					max_related_memories=self.max_related_memories,
				)
		except Exception:
			logger.exception("failed to enqueue memory post-processing task")
