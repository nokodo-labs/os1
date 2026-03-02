"""memory context filter - injects relevant memories into the system prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.models.memory import Memory
from api.v1.service.chat.filters.base import Filter
from api.v1.service.prompt_runtime import SENTINEL_USER_MEMORIES
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


class MemoryContextFilter(Filter):
	"""pre-filter that injects memory context into the system prompt.

	only activates when the admin includes {{ user_memories }} in the
	agent's system prompt. if the variable is absent, the filter is a no-op.
	"""

	name: str = Field(default="memory_context")
	description: str = Field(default="injects relevant memories into the system prompt")
	max_memories: int = Field(default=10, exclude=True)
	memory_section_header: str = Field(
		default="## user context and memories",
		exclude=True,
	)

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

		memories = await self._fetch_memories(app_context)
		content = self._format_memory_context(memories) if memories else ""

		new_text = system_text.replace(SENTINEL_USER_MEMORIES, content)
		thread.messages[system_idx] = SDKSystemMessage.from_text(new_text)

		return thread

	async def _fetch_memories(self, context: AppContext) -> list[Memory]:
		stmt = (
			select(Memory)
			.where(Memory.user_id == context.user_id)
			.order_by(Memory.updated_at.desc())
			.limit(self.max_memories)
		)

		async with AsyncSessionLocal() as tool_session:
			result = await tool_session.execute(stmt)
			items = list(result.scalars().all())
		return [mem for mem in items if isinstance(mem, Memory)]

	def _format_memory_context(self, memories: list[Memory]) -> str:
		lines = [self.memory_section_header, ""]

		for mem in memories:
			category = f" ({mem.category})" if mem.category else ""
			lines.append(f"- {mem.content}{category}")

		lines.append("")
		lines.append("use this context to personalize responses when relevant.")

		return "\n".join(lines)
