"""context compaction orchestration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.settings import settings as app_settings
from api.v1.service.chat.context_compaction.budgets import (
	DEFAULT_PROMPT_OVERHEAD_TOKENS,
	budget_for_system,
	prompt_tokens,
	setting_float,
	setting_int,
	sum_message_tokens,
	trigger_limit,
)
from api.v1.service.chat.context_compaction.budgets import (
	tool_definition_tokens as estimate_tool_definition_tokens,
)
from api.v1.service.chat.context_compaction.protection import (
	DEFAULT_RECENT_TOOL_PROTECTION_ITERATIONS,
	find_run_start_index,
)
from api.v1.service.chat.context_compaction.pruning import prune_oldest_until
from api.v1.service.chat.context_compaction.summarization import (
	build_compaction_info,
	build_summary_injection,
	inject_summary_into_system,
	next_summarization_batch,
	oldest_prefix_summary,
	replace_chat_window_sentinel,
	split_messages,
	summaries_for_branch,
)
from api.v1.service.chat.context_compaction.tool_io import apply_tool_io_cascade
from api.v1.service.chat.context_compaction.types import (
	BlockingSummarize,
	ContextCompactionProgressCallback,
	ContextCompactionResult,
)
from api.v1.service.chat.message_metadata import get_message_id
from api.v1.service.threads import summaries as summary_service
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.tool import ToolDefinition
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def _emit_compaction_progress(
	callback: ContextCompactionProgressCallback | None,
	progress: int,
	stage: str,
) -> None:
	"""emit best-effort compaction progress without failing the run."""
	if callback is None:
		return
	try:
		await callback(progress, stage)
	except Exception:
		logger.exception("failed to emit context compaction progress")


async def apply_context_compaction(
	thread: SDKThread,
	context_window: int | None,
	thread_id: TypeID,
	session: AsyncSession,
	tool_definitions: Sequence[ToolDefinition] | None = None,
	run_id: TypeID | None = None,
	iteration: int = 0,
	blocking_summarize: BlockingSummarize | None = None,
	progress_callback: ContextCompactionProgressCallback | None = None,
) -> ContextCompactionResult:
	"""project a thread into the model context using the fit-first cascade.

	the function keeps raw conversation messages whenever the full prompt fits.
	when it does not fit, it applies the ordered cascade from the refactor plan:
	tool I/O compaction, ready summary prefix swaps, blocking summarization, and
	finally protocol-valid pruning. the active run-start user message and recent
	tail tool outputs remain protected throughout, and background summarization
	is only requested for the next unsummarized old prefix.
	"""
	_ = iteration
	compaction_settings = app_settings.ai.context_compaction

	if not compaction_settings.enabled:
		cleared = replace_chat_window_sentinel(list(thread.messages), "")
		return ContextCompactionResult(
			thread=thread.model_copy(update={"messages": cleared}),
		)

	messages = list(thread.messages)
	branch_ids = [get_message_id(message) for message in messages]
	system_msgs, conversation_msgs, conversation_ids = split_messages(
		messages,
		branch_ids,
	)
	original_conv_count = len(conversation_msgs)
	tool_definition_tokens = estimate_tool_definition_tokens(tool_definitions)
	prompt_overhead_tokens = setting_int(
		compaction_settings,
		"prompt_overhead_tokens",
		DEFAULT_PROMPT_OVERHEAD_TOKENS,
	)
	protected_tool_groups = setting_int(
		compaction_settings,
		"recent_tool_output_protection_iterations",
		DEFAULT_RECENT_TOOL_PROTECTION_ITERATIONS,
	)
	base_budget = budget_for_system(
		context_window,
		system_msgs,
		tool_definition_tokens,
		prompt_overhead_tokens,
		compaction_settings.response_headroom,
	)
	full_conversation_tokens = sum_message_tokens(conversation_msgs)
	base_trigger_limit = trigger_limit(base_budget, compaction_settings.trigger_ratio)
	logger.info(
		"context compaction evaluated",
		extra={
			"thread_id": str(thread_id),
			"run_id": str(run_id) if run_id else None,
			"iteration": iteration,
			"message_count": original_conv_count,
			"conversation_tokens": full_conversation_tokens,
			"budget_tokens": base_budget,
			"trigger_tokens": base_trigger_limit,
			"context_window": context_window,
			"tool_definition_tokens": tool_definition_tokens,
			"fits": full_conversation_tokens <= base_budget,
		},
	)
	summaries_cache: list[ThreadSummary] | None = None

	async def load_agent_summaries() -> list[ThreadSummary]:
		"""load active agent-context summaries once per compaction run."""
		nonlocal summaries_cache
		if summaries_cache is None:
			summaries_cache = await summary_service.list_active_summaries(
				thread_id,
				session,
				purpose=SummaryPurpose.AGENT_CONTEXT,
			)
		return summaries_cache

	async def summarize_if_needed(
		total_tokens: int,
		budget: int,
		dropped_count: int,
	) -> tuple[bool, list[SDKMessage], TypeID | None, TypeID | None]:
		"""decide whether to enqueue a background summary batch."""
		limit = trigger_limit(budget, compaction_settings.trigger_ratio)
		if total_tokens <= limit and dropped_count == 0:
			return False, [], None, None
		summaries = await load_agent_summaries()
		usable = summaries_for_branch(
			summaries,
			conversation_ids,
			max_end_index=find_run_start_index(conversation_msgs, run_id),
		)
		batch_messages, start_id, end_id = next_summarization_batch(
			conversation_msgs,
			conversation_ids,
			usable,
			budget,
			run_id,
		)
		if batch_messages:
			logger.info(
				"context summarization requested",
				extra={
					"thread_id": str(thread_id),
					"run_id": str(run_id) if run_id else None,
					"message_count": len(batch_messages),
					"start_message_id": str(start_id) if start_id else None,
					"end_message_id": str(end_id) if end_id else None,
					"total_tokens": total_tokens,
					"budget_tokens": budget,
					"dropped_count": dropped_count,
				},
			)
		return bool(batch_messages), batch_messages, start_id, end_id

	if full_conversation_tokens <= base_budget:
		final_messages = system_msgs + conversation_msgs
		compaction_info = build_compaction_info(
			summary_count=0,
			dropped_count=0,
			total_tokens=full_conversation_tokens,
			budget_tokens=base_budget,
			original_message_count=original_conv_count,
			visible_message_count=original_conv_count,
		)
		final_messages = replace_chat_window_sentinel(
			final_messages,
			compaction_info,
		)
		if full_conversation_tokens > base_trigger_limit:
			(
				needs_summarization,
				summarize_messages,
				start_message_id,
				end_message_id,
			) = await summarize_if_needed(
				full_conversation_tokens,
				base_budget,
				0,
			)
		else:
			needs_summarization = False
			summarize_messages = []
			start_message_id = None
			end_message_id = None
		return ContextCompactionResult(
			thread=thread.model_copy(update={"messages": final_messages}),
			needs_summarization=needs_summarization,
			summarize_messages=summarize_messages,
			start_message_id=start_message_id,
			end_message_id=end_message_id,
			total_tokens=full_conversation_tokens,
			budget_tokens=base_budget,
		)

	windowed_system = system_msgs
	working_messages = list(conversation_msgs)
	working_ids = list(conversation_ids)
	budget = base_budget
	summary_count = 0
	dropped_count = 0
	compacted_tool_call_count = 0
	compacted_tool_result_count = 0
	compacted_tool_run_count = 0
	blocking_summary_count = 0

	(
		working_messages,
		total_tokens,
		tool_call_count,
		tool_result_count,
		tool_run_count,
	) = apply_tool_io_cascade(
		working_messages,
		budget,
		run_id,
		protected_tool_groups,
	)
	compacted_tool_call_count += tool_call_count
	compacted_tool_result_count += tool_result_count
	compacted_tool_run_count += tool_run_count

	if total_tokens > budget:
		summaries = await load_agent_summaries()
		usable_summaries = summaries_for_branch(
			summaries,
			conversation_ids,
			max_end_index=find_run_start_index(conversation_msgs, run_id),
		)
	else:
		usable_summaries = []

	if total_tokens > budget and usable_summaries:
		applied_summaries: list[ThreadSummary] = []
		remaining_summaries = list(usable_summaries)
		while total_tokens > budget and remaining_summaries:
			selection = oldest_prefix_summary(
				remaining_summaries,
				working_ids,
			)
			if selection is None:
				break
			summary, end_index = selection
			remaining_summaries = [
				candidate
				for candidate in remaining_summaries
				if candidate.id != summary.id
			]
			candidate_summaries = [*applied_summaries, summary]
			candidate_messages = working_messages[end_index + 1 :]
			candidate_ids = working_ids[end_index + 1 :]
			summary_text = build_summary_injection(candidate_summaries)
			candidate_system = inject_summary_into_system(system_msgs, summary_text)
			candidate_budget = budget_for_system(
				context_window,
				candidate_system,
				tool_definition_tokens,
				prompt_overhead_tokens,
				response_headroom=compaction_settings.response_headroom,
			)
			candidate_tokens = sum_message_tokens(candidate_messages)
			current_prompt_tokens = prompt_tokens(
				windowed_system,
				total_tokens,
				tool_definition_tokens,
				prompt_overhead_tokens,
			)
			candidate_prompt_tokens = prompt_tokens(
				candidate_system,
				candidate_tokens,
				tool_definition_tokens,
				prompt_overhead_tokens,
			)
			if (
				candidate_tokens > candidate_budget
				and candidate_prompt_tokens >= current_prompt_tokens
			):
				continue
			applied_summaries = candidate_summaries
			windowed_system = candidate_system
			working_messages = list(candidate_messages)
			working_ids = list(candidate_ids)
			budget = candidate_budget
			summary_count = len(applied_summaries)
			total_tokens = candidate_tokens

	blocking_enabled = bool(
		getattr(compaction_settings, "blocking_summarization_enabled", True)
	)
	if total_tokens > budget and blocking_enabled and blocking_summarize is not None:
		await _emit_compaction_progress(
			progress_callback,
			15,
			"compacting context",
		)
		while total_tokens > budget:
			batch_messages, start_id, end_id = next_summarization_batch(
				working_messages,
				working_ids,
				[],
				budget,
				run_id,
			)
			if not batch_messages or start_id is None or end_id is None:
				break
			try:
				logger.info(
					"inline context summarization started",
					extra={
						"thread_id": str(thread_id),
						"run_id": str(run_id) if run_id else None,
						"message_count": len(batch_messages),
						"start_message_id": str(start_id),
						"end_message_id": str(end_id),
						"total_tokens": total_tokens,
						"budget_tokens": budget,
					},
				)
				summary = await asyncio.wait_for(
					blocking_summarize(batch_messages, start_id, end_id),
					timeout=setting_float(
						compaction_settings,
						"blocking_summarization_timeout_seconds",
						20.0,
					),
				)
			except TimeoutError:
				logger.warning("inline context summarization timed out")
				break
			if summary is None:
				break
			blocking_summary_count += 1
			logger.info(
				"inline context summarization completed",
				extra={
					"thread_id": str(thread_id),
					"run_id": str(run_id) if run_id else None,
					"summary_id": str(summary.id),
					"message_count": len(batch_messages),
				},
			)
			windowed_system = inject_summary_into_system(
				windowed_system,
				build_summary_injection([summary]),
			)
			budget = budget_for_system(
				context_window,
				windowed_system,
				tool_definition_tokens,
				prompt_overhead_tokens,
				compaction_settings.response_headroom,
			)
			try:
				end_index = working_ids.index(str(end_id))
			except ValueError:
				break
			del working_messages[: end_index + 1]
			del working_ids[: end_index + 1]
			total_tokens = sum_message_tokens(working_messages)
			await _emit_compaction_progress(
				progress_callback,
				60,
				"context summary ready",
			)

	if total_tokens > budget:
		(
			working_messages,
			working_ids,
			total_tokens,
			dropped_count,
		) = prune_oldest_until(
			working_messages,
			working_ids,
			budget,
			run_id,
			protected_tool_groups,
		)

	(
		needs_summarization,
		summarize_messages,
		start_message_id,
		end_message_id,
	) = await summarize_if_needed(total_tokens, budget, dropped_count)

	final_messages = windowed_system + working_messages

	if dropped_count > 0:
		notice = SDKSystemMessage.from_text(
			f"[{dropped_count} earlier messages not shown]"
		)
		insert_pos = len(windowed_system)
		final_messages.insert(insert_pos, notice)

	compaction_info = build_compaction_info(
		summary_count=summary_count,
		dropped_count=dropped_count,
		total_tokens=total_tokens,
		budget_tokens=budget,
		original_message_count=original_conv_count,
		visible_message_count=len(working_messages),
		compacted_tool_call_count=compacted_tool_call_count,
		compacted_tool_result_count=compacted_tool_result_count,
		compacted_tool_run_count=compacted_tool_run_count,
		blocking_summary_count=blocking_summary_count,
	)
	final_messages = replace_chat_window_sentinel(final_messages, compaction_info)

	windowed_thread = thread.model_copy(update={"messages": final_messages})

	if (
		dropped_count > 0
		or summary_count > 0
		or compacted_tool_call_count > 0
		or compacted_tool_result_count > 0
		or compacted_tool_run_count > 0
		or blocking_summary_count > 0
	):
		logger.info(
			"context compaction: %d summaries injected, %d messages dropped, "
			"%d tool call args compacted, %d tool results compacted, "
			"%d tool runs summarized, %d inline summaries, "
			"%d/%d tokens used, "
			"summarization_needed=%s",
			summary_count,
			dropped_count,
			compacted_tool_call_count,
			compacted_tool_result_count,
			compacted_tool_run_count,
			blocking_summary_count,
			total_tokens,
			budget,
			needs_summarization,
		)

	return ContextCompactionResult(
		thread=windowed_thread,
		needs_summarization=needs_summarization,
		summarize_messages=summarize_messages,
		start_message_id=start_message_id,
		end_message_id=end_message_id,
		dropped_count=dropped_count,
		total_tokens=total_tokens,
		budget_tokens=budget,
		summary_count=summary_count,
		compacted_tool_call_count=compacted_tool_call_count,
		compacted_tool_result_count=compacted_tool_result_count,
		compacted_tool_run_count=compacted_tool_run_count,
		blocking_summary_count=blocking_summary_count,
	)
