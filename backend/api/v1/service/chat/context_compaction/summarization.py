"""agent-context summarization helpers for context compaction."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from math import floor

from pydantic import BaseModel, Field, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import session_scope
from api.models.thread import Thread
from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.settings import settings
from api.v1.service import threads as thread_service
from api.v1.service.chat.context_compaction.budgets import (
	estimate_compaction_message_tokens,
)
from api.v1.service.chat.context_compaction.protection import find_run_start_index
from api.v1.service.chat.message_metadata import persisted_message_metadata
from api.v1.service.chat.models import (
	is_context_pressure_generation_error,
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.prompt_runtime import SENTINEL_CHAT_WINDOW_INFO
from api.v1.service.threads import summaries as summary_service
from nokodo_ai.adapters.chat import GenerationBadRequestError
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.tokens import (
	CHARS_PER_TOKEN,
	DEFAULT_CONTEXT_WINDOW,
	SAFETY_MARGIN,
	estimate_tokens,
)
from nokodo_ai.utils.typeid import TypeID, is_typeid


logger = logging.getLogger(__name__)
SUMMARY_MESSAGE_METADATA_KEY = "_context_summary_id"
SUMMARY_COVERED_RAW_IDS_METADATA_KEY = (
	summary_service.SUMMARY_COVERED_RAW_IDS_METADATA_KEY
)
SUMMARY_PREDECESSOR_IDS_METADATA_KEY = "predecessor_summary_ids"
SUMMARY_BRANCH_HEAD_METADATA_KEY = "branch_head_message_id"


class SummaryRangeStaleError(RuntimeError):
	"""raised when an async summary target no longer matches the active branch."""


# max chars to send to the condensation model. computed from
# DEFAULT_CONTEXT_WINDOW (128K tokens) at ~4 chars/token, leaving
# 30% headroom for the system prompt and response.
_MAX_CONDENSATION_INPUT_CHARS = int(DEFAULT_CONTEXT_WINDOW * 4 * 0.70)

_SUMMARY_POSITIONAL_PREFIX = (
	"[compacted conversation summary replacing earlier raw messages]\n"
)

_SUMMARY_FIELD_DESCRIPTION = (
	"dense agent-context continuity summary of this exact conversation segment. "
	"preserve unique requests, constraints, corrections, artifacts, tool "
	"conclusions, failures, preferences, and unresolved work; do not explain "
	"generic subject matter"
)
_SUMMARY_FIELD_EXAMPLES = [
	(
		"the user asked the agent to draft an essay on quantum tunneling; "
		"the agent produced a structured essay covering barrier penetration, "
		"wavefunctions, applications, and analogies."
	)
]

_CONDENSE_FIELD_DESCRIPTION = (
	"single merged continuity summary preserving unique chat history from the "
	"provided summaries. remove repetition, keep chronological decisions and "
	"unresolved work, and avoid generic exposition"
)
_CONDENSE_FIELD_EXAMPLES = [
	(
		"the user iterated on a release checklist, asked for migration safety "
		"checks, accepted the service-layer approach, and left frontend wiring "
		"as the next task."
	)
]


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


def _bounded_summary_model(
	name: str,
	max_chars: int,
	description: str,
	examples: list[str],
) -> type[BaseModel]:
	"""build a pydantic structured-output model with a hard summary cap."""
	return create_model(
		name,
		summary=(
			str,
			Field(
				min_length=1,
				max_length=max_chars,
				description=description,
				examples=examples,
			),
		),
	)


def _summary_text_from_structured(
	structured: dict[str, object],
	model: type[BaseModel],
) -> str:
	"""validate structured summary output and extract text."""
	data: dict[str, object] = model.model_validate(structured).model_dump()
	summary = data.get("summary")
	if not isinstance(summary, str):
		raise ValueError("structured summary output must include summary text")
	return summary.strip()


def _minimum_saving_summary_input_tokens() -> int:
	"""return the smallest raw span that can beat the summary marker."""
	return estimate_tokens(f"{_SUMMARY_POSITIONAL_PREFIX}x") + 1


def _summary_output_max_chars_for_messages(messages: Sequence[SDKMessage]) -> int:
	"""derive the largest summary text that still saves estimated tokens."""
	covered_tokens = sum(
		estimate_compaction_message_tokens(message) for message in messages
	)
	if covered_tokens < _minimum_saving_summary_input_tokens():
		return 0
	target_tokens = covered_tokens - 1
	max_chars = max(
		1,
		floor(target_tokens * CHARS_PER_TOKEN / SAFETY_MARGIN)
		- len(_SUMMARY_POSITIONAL_PREFIX),
	)
	while (
		max_chars > 0
		and estimate_tokens(f"{_SUMMARY_POSITIONAL_PREFIX}{'x' * max_chars}")
		>= covered_tokens
	):
		max_chars -= 1
	return max_chars


def _bounded_text(text: str, max_chars: int) -> str:
	"""trim text to a non-empty character cap."""
	stripped = text.strip()
	if len(stripped) <= max_chars:
		return stripped
	trimmed = stripped[:max_chars].rstrip()
	return trimmed or stripped[:max_chars]


def _summary_typeids_from_metadata(values: object) -> list[TypeID]:
	"""parse stored predecessor summary ids from metadata."""
	if not isinstance(values, list):
		return []
	return [
		TypeID(value)
		for value in values
		if isinstance(value, str) and is_typeid(value, prefix="tsum")
	]


def _is_positional_summary_message(message: SDKMessage) -> bool:
	"""return whether a system-role message is a positional summary swap."""
	metadata = message.metadata or {}
	return isinstance(metadata.get(SUMMARY_MESSAGE_METADATA_KEY), str)


def split_messages(
	messages: list[SDKMessage],
	branch_ids: list[str | None],
) -> tuple[list[SDKMessage], list[SDKMessage], list[str | None]]:
	"""separate fixed system messages from branch conversation messages."""
	system_msgs: list[SDKMessage] = []
	conversation_msgs: list[SDKMessage] = []
	conversation_ids: list[str | None] = []

	for index, message in enumerate(messages):
		if isinstance(message, SDKSystemMessage) and not _is_positional_summary_message(
			message
		):
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


def _summary_metadata_header(summary: ThreadSummary) -> str:
	"""build a concise prompt-visible metadata line for an injected summary."""
	metadata = summary.metadata_ if isinstance(summary.metadata_, dict) else {}
	covered = metadata.get(SUMMARY_COVERED_RAW_IDS_METADATA_KEY)
	predecessors = metadata.get(SUMMARY_PREDECESSOR_IDS_METADATA_KEY)
	branch_head = metadata.get(SUMMARY_BRANCH_HEAD_METADATA_KEY)
	parts = [f"id={summary.id}"]
	if summary.start_message_id or summary.end_message_id:
		parts.append(
			f"range={summary.start_message_id or '?'}..{summary.end_message_id or '?'}"
		)
	if isinstance(covered, list) and covered:
		parts.append(f"covered_raw={len(covered)}")
	if isinstance(predecessors, list) and predecessors:
		parts.append(f"predecessors={len(predecessors)}")
	if isinstance(branch_head, str) and branch_head:
		parts.append(f"branch_head={branch_head}")
	return "[summary metadata: " + "; ".join(parts) + "]\n"


def build_positional_summary_message(summary: ThreadSummary) -> SDKSystemMessage:
	"""build a positional system message that replaces a raw covered span."""
	text = (
		f"{_SUMMARY_POSITIONAL_PREFIX}"
		f"{_summary_metadata_header(summary)}"
		f"{summary.content.strip()}"
	)
	return SDKSystemMessage.from_text(text).model_copy(
		update={"metadata": {SUMMARY_MESSAGE_METADATA_KEY: str(summary.id)}}
	)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
	"""dedupe string values without reordering them."""
	seen: set[str] = set()
	result: list[str] = []
	for value in values:
		if value in seen:
			continue
		seen.add(value)
		result.append(value)
	return result


def _json_string_list(values: list[str]) -> list[JSONValue]:
	"""return strings widened to json values for metadata."""
	return [value for value in values]


def _summary_metadata_for_messages(
	messages: list[SDKMessage],
	start_message_id: TypeID | None,
	end_message_id: TypeID | None,
) -> JSONObject:
	"""collect raw coverage and predecessor lineage for a summary bundle."""
	covered_raw_ids: list[str] = []
	predecessor_ids: list[str] = []
	for message in messages:
		metadata = message.metadata or {}
		message_id = metadata.get("_message_id")
		if isinstance(message_id, str) and message_id:
			covered_raw_ids.append(message_id)
		predecessor_id = metadata.get(SUMMARY_MESSAGE_METADATA_KEY)
		if isinstance(predecessor_id, str) and predecessor_id:
			predecessor_ids.append(predecessor_id)
	metadata: JSONObject = {}
	metadata[SUMMARY_COVERED_RAW_IDS_METADATA_KEY] = _json_string_list(
		_dedupe_preserve_order(covered_raw_ids)
	)
	metadata[SUMMARY_PREDECESSOR_IDS_METADATA_KEY] = _json_string_list(
		_dedupe_preserve_order(predecessor_ids)
	)
	if end_message_id is not None:
		metadata[SUMMARY_BRANCH_HEAD_METADATA_KEY] = str(end_message_id)
	return metadata


def _summary_coverage_indices(
	summary: ThreadSummary,
	message_ids: list[str | None],
) -> tuple[int, int] | None:
	"""return the prompt span covered by a summary in the current bundle."""
	if summary.end_message_id is None:
		return None
	positions = {
		message_id: index
		for index, message_id in enumerate(message_ids)
		if message_id is not None
	}
	end_index = positions.get(str(summary.end_message_id))
	if end_index is None:
		return None
	start_index = 0
	if summary.start_message_id is not None:
		start_index = positions.get(str(summary.start_message_id), 0)
	return start_index, end_index


def _first_uncompressed_index(message_ids: list[str | None]) -> int | None:
	"""find the first raw message still selected in the prompt bundle."""
	for index, message_id in enumerate(message_ids):
		if message_id is not None:
			return index
	return None


def oldest_positional_summary(
	summaries: list[ThreadSummary],
	messages: list[SDKMessage],
	message_ids: list[str | None],
) -> tuple[ThreadSummary, int, int, SDKMessage] | None:
	"""select the smallest saving summary for the oldest raw prompt range."""
	oldest_raw_index = _first_uncompressed_index(message_ids)
	if oldest_raw_index is None:
		return None
	candidates: list[tuple[int, ThreadSummary, int, int, SDKMessage]] = []
	for summary in summaries:
		if not summary.content.strip():
			continue
		coverage = _summary_coverage_indices(summary, message_ids)
		if coverage is None:
			continue
		start_index, end_index = coverage
		if start_index > oldest_raw_index or end_index < oldest_raw_index:
			continue
		summary_message = build_positional_summary_message(summary)
		covered_tokens = sum(
			estimate_compaction_message_tokens(message)
			for message in messages[start_index : end_index + 1]
		)
		summary_tokens = estimate_compaction_message_tokens(summary_message)
		would_save = covered_tokens - summary_tokens
		if would_save <= 0:
			continue
		candidates.append((end_index, summary, start_index, end_index, summary_message))
	if not candidates:
		return None
	_, summary, start_index, end_index, summary_message = min(
		candidates,
		key=lambda item: item[0],
	)
	return summary, start_index, end_index, summary_message


def _summarization_batch(
	messages: list[SDKMessage],
	message_ids: list[str | None],
	token_limit: int,
) -> tuple[list[SDKMessage], TypeID | None, TypeID | None]:
	"""choose an oldest-prefix batch for one summary generation call."""
	if not messages:
		return [], None, None
	minimum_input_tokens = _minimum_saving_summary_input_tokens()
	target_token_limit = max(token_limit, minimum_input_tokens)
	start_index = next(
		(index for index, message_id in enumerate(message_ids) if message_id),
		None,
	)
	if start_index is None:
		return [], None, None

	total_tokens = 0
	end_index = start_index
	for index, message in enumerate(messages[start_index:], start=start_index):
		total_tokens += estimate_compaction_message_tokens(message)
		end_index = index + 1
		if total_tokens >= target_token_limit:
			break
	if total_tokens < minimum_input_tokens:
		return [], None, None

	batch_messages = messages[start_index:end_index]
	batch_ids = message_ids[start_index:end_index]
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
	token_limit: int,
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
		max_end_index = len(messages)
	else:
		max_end_index = run_start_index
	if cutoff >= max_end_index:
		return [], None, None
	return _summarization_batch(
		messages[cutoff:max_end_index],
		message_ids[cutoff:max_end_index],
		token_limit,
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
		elif isinstance(msg, SDKAssistantMessage):
			parts: list[str] = []
			if msg.text:
				parts.append(msg.text)
			for tool_call in msg.tool_calls:
				arguments = json.dumps(
					tool_call.arguments,
					ensure_ascii=True,
					separators=(",", ":"),
					default=str,
				)
				parts.append(
					f"tool_call id={tool_call.id} name={tool_call.name} "
					f"arguments={arguments}"
				)
			text = "\n".join(parts)
		elif isinstance(msg, (SDKUserMessage, SDKSystemMessage)):
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
	max_chars: int | None = None,
) -> str:
	"""generate a minimal fallback when model summarization fails."""
	count = len(messages)
	if start_time and end_time:
		text = (
			f"[{count} messages from {start_time.isoformat()} "
			f"to {end_time.isoformat()}]"
		)
	else:
		text = f"[{count} messages - summary unavailable]"
	if max_chars is None:
		return text
	return _bounded_text(text, max_chars)


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
		input_chars = len(transcript.strip())
		max_summary_chars = min(
			_summary_output_max_chars_for_messages(messages),
			max(0, input_chars - 1),
		)
		if max_summary_chars <= 0:
			raise ValueError("summary batch is too small to compact")
		output_model = _bounded_summary_model(
			"SummaryOut",
			max_summary_chars,
			_SUMMARY_FIELD_DESCRIPTION,
			_SUMMARY_FIELD_EXAMPLES,
		)
		content: str
		log_extra: dict[str, object] = {
			"thread_id": str(thread_id),
			"purpose": SummaryPurpose.AGENT_CONTEXT.value,
			"message_count": len(messages),
			"start_message_id": str(start_message_id) if start_message_id else None,
			"end_message_id": str(end_message_id) if end_message_id else None,
			"transcript_chars": len(transcript),
			"summary_max_chars": max_summary_chars,
		}
		logger.info("agent context summary generation started", extra=log_extra)

		try:
			chat_model = await resolve_task_chat_model(session, "summarization")
			sdk_thread = SDKThread(
				messages=[
					SDKSystemMessage.from_text(
						f"{_SUMMARIZE_PROMPT}\n\n"
						f"summary must be {max_summary_chars} characters or fewer."
					),
					SDKUserMessage.from_text(transcript),
				]
			)
			structured = await run_chat_model_json_schema(
				chat_model,
				thread=sdk_thread,
				json_schema=output_model.model_json_schema(),
				purpose="summarization",
			)
			content = _summary_text_from_structured(structured, output_model)
			if not content:
				content = _placeholder_summary(messages, max_chars=max_summary_chars)
		except GenerationBadRequestError as exc:
			if is_context_pressure_generation_error(exc):
				logger.warning(
					"summarization request exceeded provider context, "
					"using placeholder",
					extra={
						**log_extra,
						"provider": exc.provider,
						"status_code": exc.status_code,
						"code": exc.code,
					},
					exc_info=True,
				)
			else:
				logger.exception(
					"summarization failed for thread %s, using placeholder",
					thread_id,
				)
			content = _placeholder_summary(messages, max_chars=max_summary_chars)
		except Exception:
			logger.exception(
				"summarization failed for thread %s, using placeholder",
				thread_id,
			)
			content = _placeholder_summary(messages, max_chars=max_summary_chars)

		summary = await summary_service.create_summary(
			thread_id=thread_id,
			purpose=SummaryPurpose.AGENT_CONTEXT,
			content=content,
			message_count=len(messages),
			start_message_id=start_message_id,
			end_message_id=end_message_id,
			session=session,
			metadata=_summary_metadata_for_messages(
				messages,
				start_message_id,
				end_message_id,
			),
		)
		predecessor_ids = summary.metadata_.get(SUMMARY_PREDECESSOR_IDS_METADATA_KEY)
		parsed_predecessor_ids = _summary_typeids_from_metadata(predecessor_ids)
		if parsed_predecessor_ids:
			await summary_service.supersede_summaries(
				parsed_predecessor_ids,
				summary.id,
				session,
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
	branch_head_message_id: TypeID | None = None,
	session: AsyncSession | None = None,
) -> TypeID:
	"""summarize a persisted active-branch message range by message ids."""
	async with session_scope(session) as session:
		branch_leaf_id = branch_head_message_id or end_message_id
		if branch_head_message_id is not None:
			thread = await session.get(Thread, str(thread_id))
			if thread is None or str(thread.current_message_id) != str(
				branch_head_message_id
			):
				raise SummaryRangeStaleError("summary branch head is stale")
		branch = await thread_service.walk_message_branch(session, branch_leaf_id)
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
	expected_branch_head_message_id: TypeID | None = None,
	session: AsyncSession | None = None,
) -> TypeID | None:
	"""merge active agent-context summaries into one replacement summary.

	condensation is summary-of-summaries maintenance, not prompt-time injection:
	when too many active summaries accumulate, this writes one merged continuity
	summary and supersedes the inputs so later compaction has fewer summary
	records to consider.
	"""
	async with session_scope(session) as session:
		if expected_branch_head_message_id is not None:
			thread = await session.get(Thread, str(thread_id))
			if thread is None or str(thread.current_message_id) != str(
				expected_branch_head_message_id
			):
				raise SummaryRangeStaleError("condensation branch head is stale")
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

		max_summary_chars = max(0, len(combined.strip()) - 1)
		if max_summary_chars <= 0:
			logger.info(
				"summary condensation skipped",
				extra={
					"thread_id": str(thread_id),
					"purpose": SummaryPurpose.AGENT_CONTEXT.value,
					"summary_count": len(existing),
					"reason": "input too small",
				},
			)
			return None
		output_model = _bounded_summary_model(
			"CondensedSummaryOut",
			max_summary_chars,
			_CONDENSE_FIELD_DESCRIPTION,
			_CONDENSE_FIELD_EXAMPLES,
		)

		total_message_count = sum(summary.message_count for summary in existing)
		covered_raw_ids: list[str] = []
		predecessor_ids: list[str] = []
		for summary in existing:
			covered = summary.metadata_.get(SUMMARY_COVERED_RAW_IDS_METADATA_KEY)
			if isinstance(covered, list):
				covered_raw_ids.extend(
					value for value in covered if isinstance(value, str)
				)
			predecessor_ids.append(str(summary.id))
			predecessors = summary.metadata_.get(SUMMARY_PREDECESSOR_IDS_METADATA_KEY)
			if isinstance(predecessors, list):
				predecessor_ids.extend(
					value for value in predecessors if isinstance(value, str)
				)
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
				"summary_max_chars": max_summary_chars,
			},
		)
		try:
			chat_model = await resolve_task_chat_model(session, "summarization")
			sdk_thread = SDKThread(
				messages=[
					SDKSystemMessage.from_text(
						f"{_CONDENSE_PROMPT}\n\n"
						f"summary must be {max_summary_chars} characters or fewer."
					),
					SDKUserMessage.from_text(combined),
				]
			)
			structured = await run_chat_model_json_schema(
				chat_model,
				thread=sdk_thread,
				json_schema=output_model.model_json_schema(),
				purpose="summary_condensation",
			)
			content = _summary_text_from_structured(structured, output_model)
			if not content:
				content = _bounded_text(combined, max_summary_chars)
		except GenerationBadRequestError as exc:
			if is_context_pressure_generation_error(exc):
				logger.warning(
					"summary condensation request exceeded provider context, "
					"concatenating existing summaries",
					extra={
						"thread_id": str(thread_id),
						"purpose": SummaryPurpose.AGENT_CONTEXT.value,
						"summary_count": len(existing),
						"input_chars": len(combined),
						"summary_max_chars": max_summary_chars,
						"provider": exc.provider,
						"status_code": exc.status_code,
						"code": exc.code,
					},
					exc_info=True,
				)
			else:
				logger.exception(
					"summary condensation failed for thread %s, "
					"concatenating existing summaries",
					thread_id,
				)
			content = _bounded_text(combined, max_summary_chars)
		except Exception:
			logger.exception(
				"summary condensation failed for thread %s, "
				"concatenating existing summaries",
				thread_id,
			)
			content = _bounded_text(combined, max_summary_chars)

		condensed_metadata: JSONObject = {}
		condensed_metadata[SUMMARY_COVERED_RAW_IDS_METADATA_KEY] = _json_string_list(
			_dedupe_preserve_order(covered_raw_ids)
		)
		condensed_metadata[SUMMARY_PREDECESSOR_IDS_METADATA_KEY] = _json_string_list(
			_dedupe_preserve_order(predecessor_ids)
		)
		condensed_metadata[SUMMARY_BRANCH_HEAD_METADATA_KEY] = (
			str(last_end) if last_end else None
		)

		condensed = await summary_service.create_summary(
			thread_id=thread_id,
			purpose=SummaryPurpose.AGENT_CONTEXT,
			content=content,
			message_count=total_message_count,
			start_message_id=first_start,
			end_message_id=last_end,
			session=session,
			metadata=condensed_metadata,
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
