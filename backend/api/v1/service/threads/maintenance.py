"""service helpers for threads and messages."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_summary import SummaryType, ThreadSummary
from api.schemas.thread import ThreadUpdate
from api.settings import settings
from api.v1.service.auth import Principal
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.chat.windowing import apply_context_windowing
from api.v1.service.threads import summaries as summary_service
from api.v1.service.threads.core import update_thread
from api.v1.service.threads.messages import get_current_branch, walk_message_branch
from api.v1.service.threads.metadata import thread_metadata_missing
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


_MAINTENANCE_PROMPT = """\
given the active chat history, generate thread maintenance data.

return:
- a concise title, emoji followed by 1-3 lowercase words
- 1-6 short lowercase tags
- a concise but complete summary of the active chat branch

preserve decisions, entities, user preferences, unresolved work, and useful
context for future replies. discard filler and raw tool output details.
"""


class _ThreadMaintenanceOut(BaseModel):
	"""structured output schema for thread maintenance."""

	title: str = Field(max_length=50)
	tags: list[str] = Field(min_length=1, max_length=6)
	summary: str = Field(min_length=1)


def _thread_eligible_for_maintenance(thread: Thread) -> bool:
	return (
		thread.deleted_at is None
		and not thread.is_temporary
		and thread.current_message_id is not None
	)


def _latest_branch_update(messages: Sequence[Message]) -> datetime | None:
	latest: datetime | None = None
	for message in messages:
		candidate = message.updated_at or message.created_at
		if latest is None or candidate > latest:
			latest = candidate
	return latest


def _summary_covers_branch(
	summary: ThreadSummary,
	thread: Thread,
	latest_branch_update: datetime | None,
) -> bool:
	if not summary.content.strip():
		return False
	if thread.current_message_id is None:
		return False
	if str(summary.end_message_id) != str(thread.current_message_id):
		return False
	if latest_branch_update is not None and summary.created_at < latest_branch_update:
		return False
	return True


async def _thread_summary_stale(thread: Thread, session: AsyncSession) -> bool:
	branch = await walk_message_branch(session, TypeID(thread.current_message_id))
	latest_branch_update = _latest_branch_update(branch)
	summaries = await summary_service.list_active_summaries(thread.id, session)
	return not any(
		_summary_covers_branch(summary, thread, latest_branch_update)
		for summary in summaries
	)


def thread_needs_mandatory_maintenance(thread: Thread) -> bool:
	"""whether missing required catalog metadata should be generated now."""
	return _thread_eligible_for_maintenance(thread) and thread_metadata_missing(thread)


async def thread_needs_deferred_maintenance(
	thread: Thread,
	session: AsyncSession,
) -> bool:
	"""whether summary-only work should wait for the inactivity timer."""
	if not _thread_eligible_for_maintenance(thread):
		return False
	if thread_metadata_missing(thread):
		return False
	return await _thread_summary_stale(thread, session)


async def thread_needs_maintenance(thread: Thread, session: AsyncSession) -> bool:
	"""whether a thread needs mandatory metadata or deferred summary work."""
	if thread_needs_mandatory_maintenance(thread):
		return True
	return await thread_needs_deferred_maintenance(thread, session)


async def list_threads_due_for_maintenance(
	session: AsyncSession,
	inactive_before: datetime,
	limit: int = 50,
	inactive_since: datetime | None = None,
) -> list[Thread]:
	"""return inactive threads whose metadata or branch summary is stale.

	args:
		inactive_before: upper bound on `last_activity_at` (threads must be
			at least this old to be considered).
		limit: maximum number of eligible threads to return.
		inactive_since: optional lower bound on `last_activity_at` so callers
			can ignore threads older than a chosen lookback window. when
			omitted, no lower bound is applied and arbitrarily old threads
			are eligible.

	results are ordered oldest-first to keep the work queue stable across
	successive sweep batches and to drain the oldest stale items first.
	"""
	stmt = select(Thread).where(
		Thread.deleted_at.is_(None),
		Thread.is_temporary.is_(False),
		Thread.current_message_id.is_not(None),
		Thread.last_activity_at <= inactive_before,
	)
	if inactive_since is not None:
		stmt = stmt.where(Thread.last_activity_at >= inactive_since)
	stmt = stmt.order_by(Thread.last_activity_at.asc()).limit(limit)
	threads = list((await session.execute(stmt)).scalars().all())
	eligible: list[Thread] = []
	for thread in threads:
		if await thread_needs_maintenance(thread, session):
			eligible.append(thread)
	return eligible


async def maintain_thread_metadata(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	observed_last_activity_at: datetime | None = None,
	replace_metadata: bool = False,
	origin_session_id: str | None = None,
) -> JSONObject:
	"""generate missing metadata and a fresh active-branch summary if needed."""
	thread = await session.get(Thread, thread_id)
	if thread is None or thread.deleted_at is not None or thread.is_temporary:
		return {"thread_id": str(thread_id), "skipped": True, "reason": "not eligible"}
	if thread.current_message_id is None:
		return {"thread_id": str(thread_id), "skipped": True, "reason": "empty thread"}
	if (
		observed_last_activity_at is not None
		and thread.last_activity_at > observed_last_activity_at
	):
		return {"thread_id": str(thread_id), "skipped": True, "reason": "active"}

	branch = await get_current_branch(thread_id, session, principal=principal)
	if not branch:
		return {"thread_id": str(thread_id), "skipped": True, "reason": "empty branch"}

	latest_branch_update = _latest_branch_update(branch)
	summaries = await summary_service.list_active_summaries(thread_id, session)
	metadata_needed = replace_metadata or thread_metadata_missing(thread)
	summary_needed = not any(
		_summary_covers_branch(summary, thread, latest_branch_update)
		for summary in summaries
	)
	if not metadata_needed and not summary_needed:
		return {"thread_id": str(thread_id), "skipped": True, "reason": "up to date"}

	sdk_messages: list[SDKMessage] = []
	for message in branch:
		sdk = message.to_sdk()
		sdk_messages.append(
			sdk.model_copy(
				update={
					"metadata": {
						**(sdk.metadata or {}),
						"message_id": str(message.id),
						"created_at": message.created_at.isoformat(),
					}
				}
			)
		)
	sdk_thread = SDKThread(messages=sdk_messages)
	ignore_existing_summaries = any(
		str(summary.end_message_id) == str(thread.current_message_id)
		and not _summary_covers_branch(summary, thread, latest_branch_update)
		for summary in summaries
	)
	if ignore_existing_summaries:
		windowing = settings.ai.windowing
		if windowing.enabled and len(sdk_thread.messages) > windowing.max_messages:
			sdk_thread = sdk_thread.model_copy(
				update={"messages": sdk_thread.messages[-windowing.max_messages :]}
			)
	else:
		sdk_thread = (
			await apply_context_windowing(
				sdk_thread,
				context_window=None,
				thread_id=thread_id,
				session=session,
			)
		).thread

	transcript_lines: list[str] = []
	for sdk_message in sdk_thread.messages:
		text = ""
		if isinstance(sdk_message, SDKToolMessage):
			text = sdk_message.tool_output or ""
		elif isinstance(
			sdk_message,
			(SDKUserMessage, SDKAssistantMessage, SDKSystemMessage),
		):
			text = sdk_message.text or ""
		text = text.strip()
		if text:
			max_chars = settings.ai.tasks.maintenance_max_chars_per_message
			if max_chars is not None:
				text = text[:max_chars]
			transcript_lines.append(f"[{sdk_message.role}]: {text}")

	chat_model = await resolve_task_chat_model(session, "thread_maintenance")
	structured = await run_chat_model_json_schema(
		chat_model,
		thread=SDKThread(
			messages=[
				SDKSystemMessage.from_text(_MAINTENANCE_PROMPT),
				SDKUserMessage.from_text("\n".join(transcript_lines)),
			]
		),
		json_schema=_ThreadMaintenanceOut.model_json_schema(),
	)
	out = _ThreadMaintenanceOut.model_validate(structured)

	updated_metadata = False
	if metadata_needed:
		update_fields: dict[str, object] = {}
		desired_title = out.title.strip().lower() or None
		if (
			(replace_metadata or (thread.title or "").strip() == "")
			and desired_title is not None
			and desired_title != thread.title
		):
			update_fields["title"] = desired_title
		if replace_metadata or not thread.tags:
			desired_tags = out.tags[:6]
			if desired_tags != (thread.tags or []):
				update_fields["tags"] = desired_tags
		if update_fields:
			update_in = ThreadUpdate.model_validate(update_fields)
			await update_thread(
				thread_id,
				update_in,
				session,
				principal=principal,
				origin_session_id=origin_session_id,
			)
			updated_metadata = True

	summary_id: TypeID | None = None
	if summary_needed:
		summary = await summary_service.create_summary(
			thread_id=thread_id,
			summary_type=SummaryType.CONDENSED if summaries else SummaryType.WINDOW,
			content=out.summary.strip(),
			message_count=len(branch),
			start_message_id=branch[0].id,
			end_message_id=TypeID(thread.current_message_id),
			session=session,
		)
		summary_id = TypeID(summary.id)
		await summary_service.supersede_summaries(
			[TypeID(summary.id) for summary in summaries if summary.id != summary_id],
			summary_id,
			session,
		)

	return {
		"thread_id": str(thread_id),
		"metadata_updated": updated_metadata,
		"summary_id": str(summary_id) if summary_id is not None else None,
		"summary_updated": summary_id is not None,
	}
