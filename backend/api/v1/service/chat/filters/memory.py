"""memory context filter - injects relevant memories into the system prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from sqlalchemy import select

from api.core.database import AsyncSessionLocal
from api.models.memory import Memory
from api.v1.service.chat.filters.base import Filter
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


class MemoryContextFilter(Filter):
	"""pre-filter that injects memory context into the system prompt."""

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
		app_context: AppContext,
	) -> SDKThread:
		memories = await self._fetch_memories(app_context)
		if not memories:
			return thread

		memory_context = self._format_memory_context(memories)

		system_idx = next(
			(i for i, m in enumerate(thread.messages) if m.role == "system"),
			None,
		)

		if system_idx is not None:
			existing = thread.messages[system_idx]
			if isinstance(existing, SDKSystemMessage) and existing.text:
				augmented_text = f"{existing.text}\n\n{memory_context}"
				thread.messages[system_idx] = SDKSystemMessage.from_text(augmented_text)
		else:
			thread.messages.insert(0, SDKSystemMessage.from_text(memory_context))

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
