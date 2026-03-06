"""memory post-processing hook - maintain and refine memories after agent execution.

runs after each agent turn to analyze the conversation and
perform memory maintenance: updating stale memories, deleting
duplicates, and consolidating related memories.

memory CREATION is handled by MemoryCreateTool (agent-driven).
memory INJECTION is handled by MemoryContextFilter (pre-filter).
this hook handles the update/delete/dedup lifecycle.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import AsyncSessionLocal
from api.models.memory import Memory
from api.schemas.memory import MemoryUpdate
from api.tasks import create_background_task
from api.v1.service.chat.hooks.base import Hook
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.memories import delete_memory, update_memory
from nokodo_ai.messages import SystemMessage, UserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

logger = logging.getLogger(__name__)

# system prompt for the post-processing LLM
_POST_PROCESSING_PROMPT = """\
you are a memory maintenance agent. you receive:
1. the latest conversation messages
2. existing memories that may be related

your job is to determine what maintenance actions to take on the
memory collection. you CANNOT create new memories - only update
or delete existing ones.

actions:
- UPDATE: modify an existing memory when information has changed,
  or consolidate closely related memories into one.
- DELETE: remove a memory when it is an exact duplicate, directly
  contradicted by conversation, or was consolidated into another.

rules:
- only use memory IDs from the provided related memories list.
- keep memories granular - prefer separate facts over combined ones.
- only consolidate when memories are inseparable or exact duplicates.
- if no maintenance is needed, return an empty actions list.
"""


class PostProcessingAction(BaseModel):
	"""a single memory maintenance action."""

	action: Literal["update", "delete"]
	id: str = Field(description="memory id to act on")
	new_content: str | None = Field(
		default=None,
		description=("updated content (required for update, omit for delete)"),
	)


class PostProcessingResponse(BaseModel):
	"""structured response from the post-processing LLM."""

	actions: list[PostProcessingAction] = Field(
		default_factory=list,
	)


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

		# schedule as background task so it doesn't block response
		create_background_task(
			self._post_process(thread, user_id, app_context),
			name=f"memory_post_processing:{user_id}",
		)

	async def _post_process(
		self,
		thread: SDKThread,
		user_id: str,
		app_context: AppContext,
	) -> None:
		"""background task: fetch memories and run LLM."""
		try:
			async with AsyncSessionLocal() as session:
				memories = await self._fetch_recent_memories(user_id, session)
				if not memories:
					return

				conversation = self._extract_recent_messages(thread)
				existing = self._format_memories(memories)

				try:
					chat_model = await resolve_task_chat_model(
						session, "memory_post_processing"
					)
				except ValueError:
					logger.debug(
						"memory post-processing skipped: no task model configured"
					)
					return

				user_content = (
					f"conversation:\n"
					f"{json.dumps(conversation)}"
					f"\n\nrelated memories:\n{existing}"
				)
				llm_thread = SDKThread(
					messages=[
						SystemMessage.from_text(_POST_PROCESSING_PROMPT),
						UserMessage.from_text(user_content),
					]
				)

				schema = PostProcessingResponse.model_json_schema()
				raw = await run_chat_model_json_schema(
					chat_model,
					thread=llm_thread,
					json_schema=schema,
				)
				result = PostProcessingResponse.model_validate(raw)

				if not result.actions:
					return

				await self._apply_actions(
					result.actions,
					memories,
					user_id,
					session,
					app_context,
				)

		except Exception:
			logger.exception(
				"memory post-processing failed for user %s",
				user_id,
			)

	async def _apply_actions(
		self,
		actions: list[PostProcessingAction],
		memories: list[Memory],
		user_id: str,
		session: AsyncSession,
		app_context: AppContext,
	) -> None:
		"""apply maintenance actions via the memory service."""
		mem_ids = {str(m.id) for m in memories}

		for act in actions:
			if act.id not in mem_ids:
				logger.warning(
					"post-processing: unknown memory id %s for user %s",
					act.id,
					user_id,
				)
				continue

			memory_id = TypeID(act.id)

			if act.action == "update" and act.new_content:
				await update_memory(
					memory_id,
					MemoryUpdate(content=act.new_content),
					session,
					app_context.principal,
				)
				logger.debug(
					"post-processing: updated memory %s",
					act.id,
				)
			elif act.action == "delete":
				await delete_memory(
					memory_id,
					session,
					app_context.principal,
				)
				logger.debug(
					"post-processing: deleted memory %s",
					act.id,
				)

		await session.commit()

	async def _fetch_recent_memories(
		self,
		user_id: str,
		session: AsyncSession,
	) -> list[Memory]:
		"""load most recently updated memories for a user."""
		stmt = (
			select(Memory)
			.where(Memory.user_id == user_id)
			.order_by(Memory.updated_at.desc())
			.limit(self.max_related_memories)
		)
		result = await session.execute(stmt)
		return list(result.scalars().all())

	def _extract_recent_messages(
		self, thread: SDKThread, count: int = 4
	) -> list[dict[str, str]]:
		"""extract the last N non-tool messages."""
		msgs: list[dict[str, str]] = []
		for m in reversed(thread.messages):
			if m.role == "tool":
				continue
			text = m.text if hasattr(m, "text") else ""
			msgs.append({"role": m.role, "content": text})
			if len(msgs) >= count:
				break
		msgs.reverse()
		return msgs

	def _format_memories(self, memories: list[Memory]) -> str:
		"""format memories as JSON for the post-processing prompt."""
		entries = []
		for mem in memories:
			entries.append(
				{
					"id": str(mem.id),
					"content": mem.content,
					"updated_at": (
						mem.updated_at.isoformat() if mem.updated_at else ""
					),
				}
			)
		return json.dumps(entries, ensure_ascii=False)
