"""context window management filter.

applies token-aware windowing as the FINAL filter in the chain,
running AFTER file resolution so that token estimates include
resolved attachment data (base64/url).

first iteration: full windowing (summary injection, message exclusion,
hard truncation) + background task scheduling (summarization,
condensation).

subsequent iterations: Layer 2 combined tool result budget guard
that prevents accumulated tool outputs from overflowing the context.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field, PrivateAttr

from api.database import async_session_local
from api.settings import settings as app_settings
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.windowing import (
	apply_context_windowing,
	enforce_combined_tool_budget,
)
from api.v1.service.threads import summaries as summary_service
from api.v1.tasks.threads import (
	start_condense_summaries_task,
	start_summarize_messages_task,
)
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

logger = logging.getLogger(__name__)


class ContextWindowingFilter(Filter):
	"""token-aware context window management.

	runs as the LAST filter in the chain so that token estimates
	include resolved file data from FileResolveFilter.

	on the first agent iteration: applies full windowing (summary
	injection, message exclusion, hard truncation) and schedules
	background summarization/condensation tasks.

	on subsequent iterations: enforces a combined token budget
	across all tool results (Layer 2 guard), compacting the
	oldest tool results when the total exceeds the budget.

	this filter is NOT optional and should NOT be in the plugin
	registry. it is always appended by the agent service so it
	runs last in the filter chain.
	"""

	name: str = Field(default="context_windowing")
	description: str = Field(
		default="token-aware context window management and tool result budget guard"
	)

	_initialized: bool = PrivateAttr(default=False)

	async def process(
		self,
		thread: SDKThread,
		app_context: AppContext | None,
	) -> SDKThread:
		if app_context is None:
			return thread

		if not self._initialized:
			self._initialized = True
			return await self._first_pass(thread, app_context)

		return await self._guard_pass(thread, app_context)

	async def _first_pass(
		self,
		thread: SDKThread,
		app_context: AppContext,
	) -> SDKThread:
		"""full windowing on the first iteration."""
		thread_id = app_context.thread_id
		if thread_id is None:
			return thread

		context_window = app_context.context_window

		windowing = await apply_context_windowing(
			thread,
			context_window=context_window,
			thread_id=thread_id,
			session=app_context.session,
		)

		# schedule durable summarization if needed. the task starter deduplicates
		# active work by thread/message range so concurrent requests do not pile up.
		if (
			windowing.needs_summarization
			and windowing.summarize_messages
			and windowing.start_message_id is not None
			and windowing.end_message_id is not None
		):
			try:
				async with async_session_local() as task_session:
					await start_summarize_messages_task(
						task_session,
						app_context.principal,
						thread_id=thread_id,
						start_message_id=windowing.start_message_id,
						end_message_id=windowing.end_message_id,
					)
			except Exception:
				logger.exception("failed to enqueue summarization task")
		elif windowing.needs_summarization and windowing.summarize_messages:
			logger.warning(
				"skipping summarization task because message ids are unavailable",
				extra={"thread_id": str(thread_id)},
			)

		# schedule condensation if too many summaries exist
		summary_count = await summary_service.count_active_summaries(
			thread_id, app_context.session
		)
		threshold = app_settings.ai.windowing.max_summaries_before_condense
		if summary_count >= threshold:
			try:
				async with async_session_local() as task_session:
					await start_condense_summaries_task(
						task_session,
						app_context.principal,
						thread_id=thread_id,
					)
			except Exception:
				logger.exception("failed to enqueue summary condensation task")

		# apply Layer 2 guard on the windowed result
		return enforce_combined_tool_budget(
			windowing.thread,
			context_window=context_window,
		)

	async def _guard_pass(
		self,
		thread: SDKThread,
		app_context: AppContext,
	) -> SDKThread:
		"""Layer 2: enforce combined tool result token budget.

		runs on every iteration after the first to catch new tool
		results that may have pushed the total over budget.
		"""
		return enforce_combined_tool_budget(
			thread,
			context_window=app_context.context_window,
		)
