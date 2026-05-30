"""context compaction orchestration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.settings import settings as app_settings
from api.v1.service.chat.context_compaction.budgets import (
	budget_for_system,
	effective_context_window,
	sum_message_tokens,
	summary_cluster_token_limit,
	trigger_limit,
)
from api.v1.service.chat.context_compaction.budgets import (
	tool_definition_tokens as estimate_tool_definition_tokens,
)
from api.v1.service.chat.context_compaction.protection import (
	find_media_protected_index,
	protected_floor_index,
)
from api.v1.service.chat.context_compaction.pruning import prune_oldest_until
from api.v1.service.chat.context_compaction.summarization import (
	build_compaction_info,
	build_positional_summary_message,
	next_summarization_batch,
	oldest_positional_summary,
	replace_chat_window_sentinel,
	split_messages,
	summaries_for_branch,
)
from api.v1.service.chat.context_compaction.tool_io import apply_tool_io_cascade
from api.v1.service.chat.context_compaction.types import (
	BlockingSummarize,
	ContextCompactionError,
	ContextCompactionProgressCallback,
	ContextCompactionResult,
	ContextCompactionTier,
	ContextCompactionTriggerReason,
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
	tool I/O compaction, ready positional summary swaps, blocking summarization,
	and finally protocol-valid pruning. the active run-start user message remains
	protected throughout, and background summarization is only requested for the
	next compressible old range.
	"""
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
	target_usage_cap_tokens = compaction_settings.target_usage_cap_tokens
	effective_window = effective_context_window(
		context_window,
		target_usage_cap_tokens,
	)
	prompt_overhead_tokens = compaction_settings.prompt_overhead_tokens
	base_budget = budget_for_system(
		effective_window,
		system_msgs,
		tool_definition_tokens,
		prompt_overhead_tokens,
		compaction_settings.response_headroom,
	)
	if base_budget <= 0:
		raise ContextCompactionError(
			"context setup exceeds the available model context window"
		)
	full_conversation_tokens = sum_message_tokens(conversation_msgs)
	soft_threshold = compaction_settings.trigger_ratio
	base_trigger_limit = trigger_limit(base_budget, soft_threshold)
	base_summary_batch_limit = summary_cluster_token_limit(
		full_conversation_tokens,
		base_budget,
		compaction_settings.recovery_target_ratio,
		compaction_settings.summary_batch_min_tokens,
		compaction_settings.summary_batch_max_tokens,
	)
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
			"trigger_ratio": soft_threshold,
			"summary_batch_tokens": base_summary_batch_limit,
			"context_window": context_window,
			"effective_context_window": effective_window,
			"target_usage_cap_tokens": target_usage_cap_tokens,
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
		limit = trigger_limit(budget, soft_threshold)
		if total_tokens <= limit and dropped_count == 0:
			return False, [], None, None
		batch_token_limit = summary_cluster_token_limit(
			total_tokens,
			budget,
			compaction_settings.recovery_target_ratio,
			compaction_settings.summary_batch_min_tokens,
			compaction_settings.summary_batch_max_tokens,
		)
		if batch_token_limit <= 0:
			return False, [], None, None
		summaries = await load_agent_summaries()
		usable = summaries_for_branch(
			summaries,
			conversation_ids,
			max_end_index=protected_floor_index(conversation_msgs, run_id),
		)
		batch_messages, start_id, end_id = next_summarization_batch(
			conversation_msgs,
			conversation_ids,
			usable,
			batch_token_limit,
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
					"summary_batch_tokens": batch_token_limit,
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
			compaction_tier="raw",
			trigger_reason="soft_pressure" if needs_summarization else "fits",
			effective_context_window=effective_window,
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
	compaction_tier: ContextCompactionTier = "raw"
	trigger_reason: ContextCompactionTriggerReason = "over_budget"

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
	)
	compacted_tool_call_count += tool_call_count
	compacted_tool_result_count += tool_result_count
	compacted_tool_run_count += tool_run_count
	if tool_call_count > 0 or tool_result_count > 0 or tool_run_count > 0:
		compaction_tier = "t1_tool_io"

	if total_tokens > budget:
		summaries = await load_agent_summaries()
		usable_summaries = summaries_for_branch(
			summaries,
			conversation_ids,
			max_end_index=protected_floor_index(conversation_msgs, run_id),
		)
	else:
		usable_summaries = []

	if total_tokens > budget and usable_summaries:
		remaining_summaries = list(usable_summaries)
		while total_tokens > budget and remaining_summaries:
			selection = oldest_positional_summary(
				remaining_summaries,
				working_messages,
				working_ids,
			)
			if selection is None:
				break
			summary, start_index, end_index, summary_message = selection
			remaining_summaries = [
				candidate
				for candidate in remaining_summaries
				if candidate.id != summary.id
			]
			working_messages = [
				*working_messages[:start_index],
				summary_message,
				*working_messages[end_index + 1 :],
			]
			working_ids = [
				*working_ids[:start_index],
				None,
				*working_ids[end_index + 1 :],
			]
			summary_count += 1
			compaction_tier = "t2_ready_summary"
			total_tokens = sum_message_tokens(working_messages)

	blocking_enabled = bool(
		getattr(compaction_settings, "blocking_summarization_enabled", True)
	)

	async def apply_blocking_summarization(total_tokens: int) -> int:
		"""run T3 inline summarization over the oldest compressible raw range."""
		nonlocal blocking_summary_count, compaction_tier, summary_count
		nonlocal working_ids, working_messages
		if not blocking_enabled or blocking_summarize is None:
			return total_tokens
		await _emit_compaction_progress(
			progress_callback,
			15,
			"compacting context",
		)
		while total_tokens > budget:
			batch_token_limit = summary_cluster_token_limit(
				total_tokens,
				budget,
				compaction_settings.recovery_target_ratio,
				compaction_settings.summary_batch_min_tokens,
				compaction_settings.summary_batch_max_tokens,
			)
			if batch_token_limit <= 0:
				break
			batch_messages, start_id, end_id = next_summarization_batch(
				working_messages,
				working_ids,
				[],
				batch_token_limit,
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
					timeout=compaction_settings.blocking_summarization_timeout_seconds,
				)
			except TimeoutError:
				logger.warning("inline context summarization timed out")
				break
			if summary is None:
				break
			logger.info(
				"inline context summarization completed",
				extra={
					"thread_id": str(thread_id),
					"run_id": str(run_id) if run_id else None,
					"summary_id": str(summary.id),
					"message_count": len(batch_messages),
				},
			)
			try:
				start_index = working_ids.index(str(start_id))
				end_index = working_ids.index(str(end_id))
			except ValueError:
				break
			candidate_messages = [
				*working_messages[:start_index],
				build_positional_summary_message(summary),
				*working_messages[end_index + 1 :],
			]
			candidate_ids = [
				*working_ids[:start_index],
				None,
				*working_ids[end_index + 1 :],
			]
			candidate_tokens = sum_message_tokens(candidate_messages)
			if candidate_tokens >= total_tokens:
				logger.warning(
					"inline context summarization did not reduce token usage",
					extra={
						"thread_id": str(thread_id),
						"run_id": str(run_id) if run_id else None,
						"summary_id": str(summary.id),
						"before_tokens": total_tokens,
						"after_tokens": candidate_tokens,
					},
				)
				break
			working_messages = candidate_messages
			working_ids = candidate_ids
			total_tokens = candidate_tokens
			blocking_summary_count += 1
			summary_count += 1
			compaction_tier = "t3_blocking_summary"
			await _emit_compaction_progress(
				progress_callback,
				60,
				"context summary ready",
			)
		return total_tokens

	if total_tokens > budget:
		total_tokens = await apply_blocking_summarization(total_tokens)

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
		)
		if dropped_count > 0:
			compaction_tier = "t4_prune"
		if total_tokens > budget:
			total_tokens = await apply_blocking_summarization(total_tokens)

	if total_tokens > budget:
		if find_media_protected_index(working_messages) is not None:
			raise ContextCompactionError(
				"unable to fit prompt: protected native media being read this turn "
				"exceeds the model context window. fetch fewer files at once or use "
				"a model with a larger context window."
			)
		raise ContextCompactionError(
			"unable to fit prompt without dropping protected active-run context"
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
			"summarization_needed=%s tier=%s",
			summary_count,
			dropped_count,
			compacted_tool_call_count,
			compacted_tool_result_count,
			compacted_tool_run_count,
			blocking_summary_count,
			total_tokens,
			budget,
			needs_summarization,
			compaction_tier,
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
		compaction_tier=compaction_tier,
		trigger_reason=trigger_reason,
		effective_context_window=effective_window,
	)
