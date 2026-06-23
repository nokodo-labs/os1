"""context compaction filter.

applies the final token-aware context compaction cascade after earlier
pre-processing filters have resolved memory, attachment state, files, and
citations.

each iteration: full token budget cascade, then background task scheduling
for summaries and summary condensation.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING

from pydantic import Field

from api.database import async_session_local
from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.v1.service.chat.context_compaction import apply_context_compaction
from api.v1.service.chat.context_compaction.summarization import summarize_messages
from api.v1.service.chat.context_compaction.types import ContextCompactionError
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import get_message_id
from api.v1.service.chat.run_activities import RunActivityEmitter, start_run_activity
from api.v1.service.threads import summaries as summary_service
from api.v1.tasks.threads import (
	start_condense_summaries_task,
	start_summarize_messages_task,
)
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

logger = logging.getLogger(__name__)


def _compaction_int_field(result: object, name: str) -> int:
	"""read an integer result field with a JSON-safe fallback."""
	value = getattr(result, name, 0)
	return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _compaction_str_field(result: object, name: str, default: str) -> str:
	"""read a string result field with a JSON-safe fallback."""
	value = getattr(result, name, default)
	return value if isinstance(value, str) else default


def _latest_context_message_id(thread: SDKThread) -> str | None:
	"""return the latest persisted non-system message id in the SDK thread."""
	for message in reversed(thread.messages):
		if isinstance(message, SDKSystemMessage):
			continue
		message_id = get_message_id(message)
		if message_id:
			return message_id
	return None


class ContextCompactionFilter(Filter):
	"""token-aware context compaction.

	runs as the last filter in the chain so token estimates include the
	resolved prompt that will be sent to the model.
	"""

	name: str = Field(default="context_compaction")
	description: str = Field(
		default=(
			"keeps model context within budget by compacting history, injecting "
			"summaries, and compacting accumulated tool results"
		)
	)

	async def process(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""apply compaction to the iteration thread when app context exists."""
		if app_context is None:
			return state

		_ = agent_context
		projected = await self._apply_compaction(state, app_context)

		state.thread = projected
		return state

	async def _apply_compaction(
		self,
		state: AgentIterationState[AppContext],
		app_context: AppContext,
	) -> SDKThread:
		"""run compaction and enqueue follow-up summary tasks."""
		thread_id = app_context.thread_id
		if thread_id is None:
			return state.thread

		context_window = app_context.context_window
		tool_definitions = [tool.definition for tool in state.tools]
		anchor_message_id = _latest_context_message_id(state.thread)
		compaction_started = False
		compaction_finished = False
		latest_progress = 0
		latest_stage = "compacting context"
		timer_task: asyncio.Task[None] | None = None
		activity: RunActivityEmitter | None = None

		async def emit_timer_ticks() -> None:
			"""emit backend-timed progress ticks while compaction is active."""
			while True:
				await asyncio.sleep(1)
				if compaction_finished:
					return
				try:
					if activity is not None:
						await activity.progress(
							message=latest_stage,
							progress=latest_progress,
						)
				except Exception:
					logger.exception("failed to emit context compaction timer tick")

		async def stop_timer() -> None:
			"""stop the backend timer task before terminal events."""
			nonlocal compaction_finished, timer_task
			compaction_finished = True
			if timer_task is None:
				return
			timer_task.cancel()
			with suppress(asyncio.CancelledError):
				await timer_task
			timer_task = None

		async def ensure_compaction_started(stage: str) -> None:
			"""emit the started event once before progress updates."""
			nonlocal activity, compaction_started, latest_stage, timer_task
			if compaction_started:
				return
			compaction_started = True
			latest_stage = stage
			activity = await start_run_activity(
				app_context,
				activity_type="context_compaction",
				message_id=anchor_message_id,
				title="compacting chat",
				message=stage,
			)
			if activity is not None:
				timer_task = asyncio.create_task(
					emit_timer_ticks(), name="context_compaction_timer"
				)

		async def progress(progress: int, stage: str) -> None:
			"""emit a progress event and lazily mark compaction started."""
			nonlocal latest_progress, latest_stage
			await ensure_compaction_started(stage)
			latest_progress = progress
			latest_stage = stage
			if activity is not None:
				await activity.progress(message=stage, progress=progress)

		async def blocking_summarize(
			messages: list[SDKMessage],
			start_message_id: TypeID | None,
			end_message_id: TypeID | None,
		) -> ThreadSummary | None:
			"""generate and reload an inline summary during blocking compaction."""
			await progress(25, "summarizing old context")
			summary_id = await summarize_messages(
				thread_id=thread_id,
				messages=messages,
				start_message_id=start_message_id,
				end_message_id=end_message_id,
				session=app_context.session,
			)
			await progress(50, "loading context summary")
			return await summary_service.get_summary(summary_id, app_context.session)

		try:
			compaction = await apply_context_compaction(
				state.thread,
				context_window=context_window,
				thread_id=thread_id,
				session=app_context.session,
				tool_definitions=tool_definitions,
				run_id=app_context.run_id,
				iteration=state.iteration,
				blocking_summarize=blocking_summarize,
				progress_callback=progress,
			)
		except ContextCompactionError as exc:
			if not compaction_started:
				activity = await start_run_activity(
					app_context,
					activity_type="context_compaction",
					message_id=anchor_message_id,
					title="context limit reached",
					message=str(exc),
				)
			if activity is not None:
				await stop_timer()
				await activity.ended(
					outcome="error",
					message=str(exc),
					error=exc.__class__.__name__,
				)
			raise
		except Exception as exc:
			if compaction_started and activity is not None:
				await stop_timer()
				await activity.ended(
					outcome="error",
					message=latest_stage,
					error=exc.__class__.__name__,
				)
			raise

		if compaction_started and activity is not None:
			await stop_timer()
			await activity.ended(
				outcome="success",
				message=latest_stage,
				data={
					"tier": _compaction_str_field(compaction, "compaction_tier", "raw"),
					"trigger_reason": _compaction_str_field(
						compaction, "trigger_reason", "fits"
					),
					"total_tokens": _compaction_int_field(compaction, "total_tokens"),
					"budget_tokens": _compaction_int_field(compaction, "budget_tokens"),
					"summary_count": _compaction_int_field(compaction, "summary_count"),
					"dropped_count": _compaction_int_field(compaction, "dropped_count"),
					"compacted_tool_call_count": _compaction_int_field(
						compaction, "compacted_tool_call_count"
					),
					"compacted_tool_result_count": _compaction_int_field(
						compaction, "compacted_tool_result_count"
					),
					"compacted_tool_run_count": _compaction_int_field(
						compaction, "compacted_tool_run_count"
					),
				},
			)

		if (
			compaction.needs_summarization
			and compaction.summarize_messages
			and compaction.start_message_id is not None
			and compaction.end_message_id is not None
		):
			try:
				async with async_session_local() as task_session:
					await start_summarize_messages_task(
						task_session,
						app_context.principal,
						thread_id=thread_id,
						start_message_id=compaction.start_message_id,
						end_message_id=compaction.end_message_id,
						branch_head_message_id=anchor_message_id,
					)
				logger.info(
					"background context summarization enqueued",
					extra={
						"thread_id": str(thread_id),
						"run_id": str(app_context.run_id)
						if app_context.run_id
						else None,
						"message_count": len(compaction.summarize_messages),
						"start_message_id": str(compaction.start_message_id),
						"end_message_id": str(compaction.end_message_id),
					},
				)
			except Exception:
				logger.exception("failed to enqueue summarization task")
		elif compaction.needs_summarization and compaction.summarize_messages:
			logger.warning(
				"skipping summarization task because message ids are unavailable",
				extra={"thread_id": str(thread_id)},
			)

		summary_count = await summary_service.count_active_summaries(
			thread_id,
			app_context.session,
			purpose=SummaryPurpose.AGENT_CONTEXT,
		)
		if summary_count >= 2:
			try:
				async with async_session_local() as task_session:
					await start_condense_summaries_task(
						task_session,
						app_context.principal,
						thread_id=thread_id,
						branch_head_message_id=anchor_message_id,
					)
				logger.info(
					"summary condensation enqueued",
					extra={
						"thread_id": str(thread_id),
						"run_id": str(app_context.run_id)
						if app_context.run_id
						else None,
						"summary_count": summary_count,
					},
				)
			except Exception:
				logger.exception("failed to enqueue summary condensation task")

		return compaction.thread
