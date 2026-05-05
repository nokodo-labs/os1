"""context summarization - background task for compressing conversation history.

provides two entry points:
- summarize_messages: condense a batch of messages into a summary
- condense_summaries: merge multiple summaries into one (summary-of-summaries)

both functions use the configured summarization task model and persist
results via the thread_summaries service.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api.database import session_scope
from api.models.thread_summary import SummaryType
from api.settings import settings
from api.v1.service import threads as thread_service
from api.v1.service.chat.message_metadata import persisted_message_metadata
from api.v1.service.chat.models import resolve_task_chat_model
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
summarize the following conversation segment concisely.

preserve:
- key decisions and conclusions reached
- entities mentioned (names, files, URLs, identifiers)
- user preferences and instructions expressed
- any commitments or action items
- the emotional/tonal context if relevant

discard:
- pleasantries and filler
- redundant exchanges
- formatting noise
- tool result raw data (keep only conclusions/key findings)

respond with ONLY the summary text, no preamble or formatting."""

_CONDENSE_PROMPT = """\
the following are consecutive summaries of an ongoing conversation.
merge them into a single, concise summary that preserves all key
information without repetition.

respond with ONLY the merged summary text, no preamble or formatting."""


def _format_transcript(messages: Sequence[SDKMessage]) -> str:
	"""format a list of SDK messages into a plain transcript."""
	lines: list[str] = []
	max_chars = settings.ai.windowing.summarization_max_chars_per_message
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
	"""generate a minimal placeholder when LLM summarization fails."""
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
	"""summarize a batch of messages and persist the result.

	returns the ID of the created ThreadSummary.

	if the LLM call fails, falls back to a placeholder summary
	so that windowing can still proceed (graceful degradation).
	"""
	async with session_scope(session) as session:
		transcript = _format_transcript(messages)
		content: str

		try:
			chat_model = await resolve_task_chat_model(session, "summarization")
			sdk_thread = SDKThread(
				messages=[
					SDKSystemMessage.from_text(_SUMMARIZE_PROMPT),
					SDKUserMessage.from_text(transcript),
				]
			)
			assistant = await chat_model.generate(sdk_thread, stream=False)
			content = (assistant.text or "").strip()
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
			summary_type=SummaryType.WINDOW,
			content=content,
			message_count=len(messages),
			start_message_id=start_message_id,
			end_message_id=end_message_id,
			session=session,
		)
		return summary.id


async def summarize_thread_message_range(
	thread_id: TypeID,
	start_message_id: TypeID,
	end_message_id: TypeID,
	session: AsyncSession | None = None,
) -> TypeID:
	"""summarize a persisted branch range by message ids."""
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
	"""condense all active summaries for a thread into one.

	if fewer than 2 active summaries exist, returns None (nothing to condense).

	returns the ID of the new condensed summary, or None if skipped.
	"""
	async with session_scope(session) as session:
		existing = await summary_service.list_active_summaries(thread_id, session)
		if len(existing) < 2:
			return None

		# build a transcript of the existing summaries
		summary_texts = [s.content for s in existing if s.content]
		combined = "\n---\n".join(summary_texts)

		# cap the input to prevent overflowing the summarization model's
		# own context window. keep the beginning (oldest context) since
		# the model will produce a fresh merged summary.
		if len(combined) > _MAX_CONDENSATION_INPUT_CHARS:
			logger.warning(
				"condensation input for thread %s truncated: %d -> %d chars",
				thread_id,
				len(combined),
				_MAX_CONDENSATION_INPUT_CHARS,
			)
			combined = combined[:_MAX_CONDENSATION_INPUT_CHARS]

		total_message_count = sum(s.message_count for s in existing)

		# determine the overall message range covered
		first_start = next(
			(s.start_message_id for s in existing if s.start_message_id),
			None,
		)
		last_end = next(
			(s.end_message_id for s in reversed(existing) if s.end_message_id),
			None,
		)

		content: str
		try:
			chat_model = await resolve_task_chat_model(session, "summarization")
			sdk_thread = SDKThread(
				messages=[
					SDKSystemMessage.from_text(_CONDENSE_PROMPT),
					SDKUserMessage.from_text(combined),
				]
			)
			assistant = await chat_model.generate(sdk_thread, stream=False)
			content = (assistant.text or "").strip()
			if not content:
				content = combined  # keep the raw concatenation as fallback
		except Exception:
			logger.exception(
				"summary condensation failed for thread %s, "
				"concatenating existing summaries",
				thread_id,
			)
			content = combined

		condensed = await summary_service.create_summary(
			thread_id=thread_id,
			summary_type=SummaryType.CONDENSED,
			content=content,
			message_count=total_message_count,
			start_message_id=first_start,
			end_message_id=last_end,
			session=session,
		)

		# mark old summaries as superseded
		old_ids = [s.id for s in existing]
		await summary_service.supersede_summaries(
			old_ids,
			condensed.id,
			session,
		)

		return condensed.id
