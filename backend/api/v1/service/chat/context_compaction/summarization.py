"""agent-context summarization helpers for context compaction."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import session_scope
from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.settings import settings
from api.v1.service import threads as thread_service
from api.v1.service.chat.context_compaction.budgets import (
	estimate_compaction_message_tokens,
	summary_cluster_token_limit,
)
from api.v1.service.chat.context_compaction.protection import find_run_start_index
from api.v1.service.chat.message_metadata import persisted_message_metadata
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.prompt_runtime import SENTINEL_CHAT_WINDOW_INFO
from api.v1.service.threads import summaries as summary_service
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.tokens import DEFAULT_CONTEXT_WINDOW
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

# max chars to send to the condensation model. computed from
# DEFAULT_CONTEXT_WINDOW (128K tokens) at ~4 chars/token, leaving
# 30% headroom for the system prompt and response.
_MAX_CONDENSATION_INPUT_CHARS = int(DEFAULT_CONTEXT_WINDOW * 4 * 0.70)


_SUMMARIZE_PROMPT = """\
write an agent-context summary of the conversation segment.

the goal is future continuity, not teaching the topic. summarize what happened
in this chat, not the general subject matter. common knowledge should only be
named as a topic label unless the user or agent made a unique claim about it.
write densely: every sentence should help a future agent resume the exact chat
with minimal loss.

preserve:
- unique user requests, constraints, corrections, and preferences
- agent actions, artifacts produced, files/URLs/IDs/names, decisions, failures,
  and unresolved next steps
- tool outcomes and conclusions, not raw tool output
- the reason a tool was called, what changed because of it, and any important
	errors or constraints discovered
- emotional or interpersonal context only when it changes how to continue

discard:
- generic explanations anyone could reconstruct later
- pleasantries, filler, repeated wording, markdown noise, and raw data dumps

for ordinary generated content, say what was requested and name the sections or
topics covered without re-explaining them.

return the summary field only; no preamble or formatting outside the schema."""

_CONDENSE_PROMPT = """\
the following are consecutive agent-context summaries of an ongoing
conversation. merge them into one continuity summary.

preserve unique requests, constraints, decisions, artifacts, files, URLs,
identifiers, tool conclusions, failures, preferences, and unresolved work.
remove repetition and do not expand generic subject-matter explanations.

return the summary field only; no preamble or formatting outside the schema."""


class _SummaryOut(BaseModel):
	"""structured output schema for agent-context summaries."""

	summary: str = Field(
		min_length=1,
		description=(
			"dense agent-context continuity summary of this exact conversation "
			"segment. preserve unique requests, constraints, corrections, "
			"artifacts, tool conclusions, failures, preferences, and unresolved work; "
			"do not explain generic subject matter"
		),
		examples=[
			(
				"the user asked the agent to draft an essay on quantum tunneling; "
				"the agent produced a structured essay covering barrier penetration, "
				"wavefunctions, applications, and analogies."
			)
		],
	)


class _CondensedSummaryOut(BaseModel):
	"""structured output schema for merged agent-context summaries."""

	summary: str = Field(
		min_length=1,
		description=(
			"single merged continuity summary preserving unique chat history from "
			"the provided summaries. remove repetition, keep chronological decisions "
			"and unresolved work, and avoid generic exposition"
		),
		examples=[
			(
				"the user iterated on a release checklist, asked for migration safety "
				"checks, accepted the service-layer approach, and left frontend wiring "
				"as the next task."
			)
		],
	)


def split_messages(
	messages: list[SDKMessage],
	branch_ids: list[str | None],
) -> tuple[list[SDKMessage], list[SDKMessage], list[str | None]]:
	"""separate system messages from branch conversation messages."""
	system_msgs: list[SDKMessage] = []
	conversation_msgs: list[SDKMessage] = []
	conversation_ids: list[str | None] = []

	for index, message in enumerate(messages):
		if isinstance(message, SDKSystemMessage):
			system_msgs.append(message)
		else:
			conversation_msgs.append(message)
			conversation_ids.append(branch_ids[index])

	return system_msgs, conversation_msgs, conversation_ids


def summaries_for_branch(
	summaries: list[ThreadSummary],
	branch_ids: list[str | None],
	max_end_index: int | None = None,
) -> list[ThreadSummary]:
	"""filter summaries that can safely describe this active branch.

	a summary is usable only when it has content and its recorded end message is
	still present on the branch being projected into the model context. callers can
	also supply a maximum end index to exclude summaries that would cross protected
	messages such as the run-start user turn.
	"""
	branch_positions = {
		message_id: index
		for index, message_id in enumerate(branch_ids)
		if message_id is not None
	}
	usable: list[ThreadSummary] = []
	for summary in summaries:
		if not summary.end_message_id or not summary.content.strip():
			continue
		position = branch_positions.get(str(summary.end_message_id))
		if position is None:
			continue
		if max_end_index is not None and position >= max_end_index:
			continue
		usable.append(summary)
	return usable


def oldest_prefix_summary(
	summaries: list[ThreadSummary],
	message_ids: list[str | None],
) -> tuple[ThreadSummary, int] | None:
	"""select the smallest ready summary that replaces the current raw prefix.

	prompt-time summary injection is only valid for prefix coverage: a stored
	summary can replace messages up to its end id only when its optional start id
	is absent from the remaining visible window or starts at index zero. summaries
	that begin later would leave a gap, so they wait until older messages have been
	removed or summarized first.
	"""
	positions = {
		message_id: index
		for index, message_id in enumerate(message_ids)
		if message_id is not None
	}
	candidates: list[tuple[int, ThreadSummary]] = []
	for summary in summaries:
		if summary.end_message_id is None:
			continue
		end_index = positions.get(str(summary.end_message_id))
		if end_index is None:
			continue
		if summary.start_message_id is not None:
			start_index = positions.get(str(summary.start_message_id))
			if start_index is not None and start_index > 0:
				continue
		candidates.append((end_index, summary))
	if not candidates:
		return None
	end_index, summary = min(candidates, key=lambda item: item[0])
	return summary, end_index


def _summarization_batch(
	messages: list[SDKMessage],
	message_ids: list[str | None],
	token_limit: int,
) -> tuple[list[SDKMessage], TypeID | None, TypeID | None]:
	"""choose an oldest-prefix batch for one summary generation call."""
	if not messages:
		return [], None, None

	total_tokens = 0
	end_index = 0
	for index, message in enumerate(messages):
		total_tokens += estimate_compaction_message_tokens(message)
		end_index = index + 1
		if total_tokens >= token_limit:
			break

	batch_messages = messages[:end_index]
	batch_ids = message_ids[:end_index]
	first_id = next((message_id for message_id in batch_ids if message_id), None)
	last_id = next(
		(message_id for message_id in reversed(batch_ids) if message_id),
		None,
	)
	return (
		batch_messages,
		TypeID(first_id) if first_id else None,
		TypeID(last_id) if last_id else None,
	)


def next_summarization_batch(
	messages: list[SDKMessage],
	message_ids: list[str | None],
	summaries: list[ThreadSummary],
	budget: int,
	run_id: TypeID | None,
) -> tuple[list[SDKMessage], TypeID | None, TypeID | None]:
	"""choose the next old unsummarized batch for background or blocking work.

	the batch starts just after the newest summary cutoff and ends before the
	current run-start anchor. that keeps active-run context raw while still moving
	the oldest compressible prefix forward in token-sized chunks.
	"""
	cutoff = find_summarized_cutoff(summaries, message_ids)
	run_start_index = find_run_start_index(messages, run_id)
	if run_start_index is None:
		max_end_index = max(len(messages) - 1, 0)
	else:
		max_end_index = run_start_index
	if cutoff >= max_end_index:
		return [], None, None
	return _summarization_batch(
		messages[cutoff:max_end_index],
		message_ids[cutoff:max_end_index],
		summary_cluster_token_limit(budget),
	)


def find_summarized_cutoff(
	summaries: list[ThreadSummary],
	branch_ids: list[str | None],
) -> int:
	"""find the first branch index that is not covered by ready summaries."""
	if not summaries:
		return 0

	end_ids: set[str] = set()
	for summary in summaries:
		if summary.end_message_id:
			end_ids.add(str(summary.end_message_id))

	if not end_ids:
		return 0

	max_cutoff = 0
	for index, message_id in enumerate(branch_ids):
		if message_id and message_id in end_ids:
			max_cutoff = max(max_cutoff, index + 1)

	return max_cutoff


def build_summary_injection(summaries: list[ThreadSummary]) -> str:
	"""build the summary text to inject into the system message."""
	if not summaries:
		return ""

	parts: list[str] = []
	for summary in summaries:
		if summary.content:
			parts.append(summary.content)

	if not parts:
		return ""

	combined = "\n---\n".join(parts)
	return (
		"\n\n## conversation history summary\n\n"
		"the following is a summary of earlier messages in this conversation "
		"that have been compacted to save context space:\n\n"
		f"{combined}"
	)


def inject_summary_into_system(
	messages: list[SDKMessage],
	summary_text: str,
) -> list[SDKMessage]:
	"""append summary text to the system message."""
	if not summary_text:
		return messages

	result = list(messages)
	for index, message in enumerate(result):
		if isinstance(message, SDKSystemMessage):
			existing = message.text or ""
			new_text = existing + summary_text
			result[index] = SDKSystemMessage.from_text(new_text)
			return result

	result.insert(0, SDKSystemMessage.from_text(summary_text.strip()))
	return result


def build_compaction_info(
	summary_count: int,
	dropped_count: int,
	total_tokens: int,
	budget_tokens: int,
	original_message_count: int,
	visible_message_count: int,
	compacted_tool_call_count: int = 0,
	compacted_tool_result_count: int = 0,
	compacted_tool_run_count: int = 0,
	blocking_summary_count: int = 0,
) -> str:
	"""build the compact status line that replaces the prompt sentinel.

	this text is intentionally short because it enters the model context on every
	compacted turn. it names only behaviorally relevant losses or rewrites so the
	agent knows whether earlier messages were summarized, tool I/O was compacted,
	or hard pruning was needed.
	"""
	parts: list[str] = []

	if summary_count > 0:
		parts.append(
			f"{summary_count} summary/summaries of earlier messages are included above"
		)

	summarized_or_pruned = original_message_count - visible_message_count
	if summarized_or_pruned > 0:
		parts.append(
			f"{summarized_or_pruned} earlier messages have been summarized or pruned"
		)

	if dropped_count > 0:
		parts.append(f"{dropped_count} messages were pruned to fit the context window")
	if compacted_tool_call_count > 0:
		parts.append(
			f"{compacted_tool_call_count} old tool call argument payloads "
			"were compacted"
		)
	if compacted_tool_result_count > 0:
		parts.append(
			f"{compacted_tool_result_count} old tool result payloads were compacted"
		)
	if compacted_tool_run_count > 0:
		parts.append(f"{compacted_tool_run_count} old tool runs were summarized")
	if blocking_summary_count > 0:
		parts.append(
			f"{blocking_summary_count} inline summary/summaries were generated"
		)

	parts.append(f"you are seeing {visible_message_count} recent messages")

	if budget_tokens > 0:
		usage_pct = int(total_tokens / budget_tokens * 100)
		parts.append(f"context usage: ~{usage_pct}% of available budget")

	return "[context compaction info: " + "; ".join(parts) + "]"


def replace_chat_window_sentinel(
	messages: list[SDKMessage],
	compaction_info: str,
) -> list[SDKMessage]:
	"""replace <<FILTER:chat_window_info>> sentinel in system messages."""
	result = list(messages)
	for index, message in enumerate(result):
		if isinstance(message, SDKSystemMessage):
			text = message.text or ""
			if SENTINEL_CHAT_WINDOW_INFO in text:
				new_text = text.replace(SENTINEL_CHAT_WINDOW_INFO, compaction_info)
				result[index] = SDKSystemMessage.from_text(new_text)
	return result


def _format_transcript(messages: Sequence[SDKMessage]) -> str:
	"""format persisted SDK messages into the transcript sent for summarization."""
	lines: list[str] = []
	max_chars = settings.ai.context_compaction.summarization_max_chars_per_message
	for msg in messages:
		role = msg.role
		if isinstance(msg, SDKToolMessage):
			text = msg.tool_output or ""
		elif isinstance(msg, (SDKUserMessage, SDKAssistantMessage, SDKSystemMessage)):
			text = msg.text or ""
		else:
			text = ""
		if max_chars is not None:
			text = text[:max_chars]
		if text:
			lines.append(f"[{role}]: {text}")
	return "\n".join(lines)


def _placeholder_summary(
	messages: Sequence[SDKMessage],
	start_time: datetime | None = None,
	end_time: datetime | None = None,
) -> str:
	"""generate a minimal fallback when model summarization fails."""
	count = len(messages)
	if start_time and end_time:
		return (
			f"[{count} messages from {start_time.isoformat()} "
			f"to {end_time.isoformat()}]"
		)
	return f"[{count} messages - summary unavailable]"


async def summarize_messages(
	thread_id: TypeID,
	messages: list[SDKMessage],
	start_message_id: TypeID | None = None,
	end_message_id: TypeID | None = None,
	session: AsyncSession | None = None,
) -> TypeID:
	"""generate and persist an agent-context summary for a message batch.

	this is the background/blocking compaction summary writer. it receives an
	already selected oldest-prefix batch, asks the configured summarization model
	for a structured `summary` field, and stores the result as an
	`agent_context` summary covering the supplied message ids. failures degrade to
	a placeholder so context compaction can keep moving instead of dropping more
	conversation history.
	"""
	async with session_scope(session) as session:
		transcript = _format_transcript(messages)
		content: str
		log_extra: dict[str, object] = {
			"thread_id": str(thread_id),
			"purpose": SummaryPurpose.AGENT_CONTEXT.value,
			"message_count": len(messages),
			"start_message_id": str(start_message_id) if start_message_id else None,
			"end_message_id": str(end_message_id) if end_message_id else None,
			"transcript_chars": len(transcript),
		}
		logger.info("agent context summary generation started", extra=log_extra)

		try:
			chat_model = await resolve_task_chat_model(session, "summarization")
			sdk_thread = SDKThread(
				messages=[
					SDKSystemMessage.from_text(_SUMMARIZE_PROMPT),
					SDKUserMessage.from_text(transcript),
				]
			)
			structured = await run_chat_model_json_schema(
				chat_model,
				thread=sdk_thread,
				json_schema=_SummaryOut.model_json_schema(),
				purpose="summarization",
			)
			content = _SummaryOut.model_validate(structured).summary.strip()
			if not content:
				content = _placeholder_summary(messages)
		except Exception:
			logger.exception(
				"summarization failed for thread %s, using placeholder",
				thread_id,
			)
			content = _placeholder_summary(messages)

		summary = await summary_service.create_summary(
			thread_id=thread_id,
			purpose=SummaryPurpose.AGENT_CONTEXT,
			content=content,
			message_count=len(messages),
			start_message_id=start_message_id,
			end_message_id=end_message_id,
			session=session,
		)
		logger.info(
			"agent context summary stored",
			extra={
				**log_extra,
				"summary_id": str(summary.id),
				"summary_chars": len(content),
			},
		)
		return summary.id


async def summarize_thread_message_range(
	thread_id: TypeID,
	start_message_id: TypeID,
	end_message_id: TypeID,
	session: AsyncSession | None = None,
) -> TypeID:
	"""summarize a persisted active-branch message range by message ids."""
	async with session_scope(session) as session:
		branch = await thread_service.walk_message_branch(session, end_message_id)
		ids = [str(message.id) for message in branch]
		try:
			start_index = ids.index(str(start_message_id))
			end_index = ids.index(str(end_message_id))
		except ValueError as exc:
			raise ValueError("message range is not on the active branch") from exc
		if start_index > end_index:
			raise ValueError("start message must come before end message")

		messages: list[SDKMessage] = []
		for message in branch[start_index : end_index + 1]:
			sdk = message.to_sdk()
			messages.append(
				sdk.model_copy(
					update={
						"metadata": {
							**(sdk.metadata or {}),
							**persisted_message_metadata(
								message.id,
								message.created_at,
								message.sender_user_id,
							),
						}
					}
				)
			)
		return await summarize_messages(
			thread_id=thread_id,
			messages=messages,
			start_message_id=start_message_id,
			end_message_id=end_message_id,
			session=session,
		)


async def condense_summaries(
	thread_id: TypeID,
	session: AsyncSession | None = None,
) -> TypeID | None:
	"""merge active agent-context summaries into one replacement summary.

	condensation is summary-of-summaries maintenance, not prompt-time injection:
	when too many active summaries accumulate, this writes one merged continuity
	summary and supersedes the inputs so later compaction has fewer summary
	records to consider.
	"""
	async with session_scope(session) as session:
		existing = await summary_service.list_active_summaries(
			thread_id,
			session,
			purpose=SummaryPurpose.AGENT_CONTEXT,
		)
		if len(existing) < 2:
			logger.info(
				"summary condensation skipped",
				extra={
					"thread_id": str(thread_id),
					"purpose": SummaryPurpose.AGENT_CONTEXT.value,
					"summary_count": len(existing),
				},
			)
			return None

		summary_texts = [summary.content for summary in existing if summary.content]
		combined = "\n---\n".join(summary_texts)

		if len(combined) > _MAX_CONDENSATION_INPUT_CHARS:
			logger.warning(
				"condensation input for thread %s truncated: %d -> %d chars",
				thread_id,
				len(combined),
				_MAX_CONDENSATION_INPUT_CHARS,
			)
			combined = combined[:_MAX_CONDENSATION_INPUT_CHARS]

		total_message_count = sum(summary.message_count for summary in existing)
		first_start = next(
			(
				summary.start_message_id
				for summary in existing
				if summary.start_message_id
			),
			None,
		)
		last_end = next(
			(
				summary.end_message_id
				for summary in reversed(existing)
				if summary.end_message_id
			),
			None,
		)

		content: str
		logger.info(
			"summary condensation started",
			extra={
				"thread_id": str(thread_id),
				"purpose": SummaryPurpose.AGENT_CONTEXT.value,
				"summary_count": len(existing),
				"input_chars": len(combined),
			},
		)
		try:
			chat_model = await resolve_task_chat_model(session, "summarization")
			sdk_thread = SDKThread(
				messages=[
					SDKSystemMessage.from_text(_CONDENSE_PROMPT),
					SDKUserMessage.from_text(combined),
				]
			)
			structured = await run_chat_model_json_schema(
				chat_model,
				thread=sdk_thread,
				json_schema=_CondensedSummaryOut.model_json_schema(),
				purpose="summary_condensation",
			)
			content = _CondensedSummaryOut.model_validate(structured).summary.strip()
			if not content:
				content = combined
		except Exception:
			logger.exception(
				"summary condensation failed for thread %s, "
				"concatenating existing summaries",
				thread_id,
			)
			content = combined

		condensed = await summary_service.create_summary(
			thread_id=thread_id,
			purpose=SummaryPurpose.AGENT_CONTEXT,
			content=content,
			message_count=total_message_count,
			start_message_id=first_start,
			end_message_id=last_end,
			session=session,
		)

		old_ids = [summary.id for summary in existing]
		await summary_service.supersede_summaries(
			old_ids,
			condensed.id,
			session,
		)
		logger.info(
			"summary condensation stored",
			extra={
				"thread_id": str(thread_id),
				"purpose": SummaryPurpose.AGENT_CONTEXT.value,
				"summary_id": str(condensed.id),
				"superseded_count": len(old_ids),
				"summary_chars": len(content),
			},
		)

		return condensed.id
