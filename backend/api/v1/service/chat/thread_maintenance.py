"""thread maintenance: LLM-generated catalog metadata (title, tags, summary).

this is chat-tier orchestration that operates on threads - it drives context
compaction + chat models to summarize a thread, then writes the result back via
the threads data tier. it lives under ``chat`` (not ``threads``) so the
dependency stays one-way ``chat -> threads``; the threads facade never imports
the chat domain.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import async_shared_broker

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.models.message import Message
from api.models.task import Task, TaskStatus, TaskType
from api.models.thread import Thread
from api.models.thread_passage import ThreadPassage
from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.permissions import ResourceType
from api.runtime import on_settings_reload
from api.schemas.thread import ThreadUpdate
from api.settings import settings
from api.taskiq import redis_schedule_source
from api.v1.service.authentication import Principal, load_principal_for_user
from api.v1.service.authorization import fetch_bulk_acl_metadata
from api.v1.service.chat.context_compaction import apply_context_compaction
from api.v1.service.chat.context_compaction.tasks import (
	CHAT_CONDENSE_SUMMARIES_TASK,
	CHAT_SUMMARIZE_MESSAGES_TASK,
)
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.memories import MEMORY_POST_PROCESSING_TASK
from api.v1.service.tasks import (
	fail_stale_active_tasks,
	find_active_task,
	start_task,
	update_task_execution,
)
from api.v1.service.threads import (
	THREAD_SPEC,
	get_current_branch,
	reconcile_thread_content_vectors,
	update_thread,
	walk_message_branch,
)
from api.v1.service.threads.content_vectors import (
	content_vectors_due_predicate,
	passage_generation_params,
)
from api.v1.service.threads.passages import (
	TranscriptPassage,
	build_transcript_passages,
	list_unenriched_passages,
)
from api.v1.service.threads.summaries import (
	create_summary,
	latest_active_summary_text,
	list_active_summaries,
	supersede_summaries,
)
from api.v1.service.threads.user_state import (
	state_vectors_due_predicate,
	sync_thread_state_vectors,
)
from api.v1.service.threads.vectorization import schedule_thread_content_vectorization
from api.v1.service.vectorize import vectorize_resource
from api.v1.service.vectorstores import get_collection
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.typeid import TypeID
from nokodo_ai.utils.validators import validate_single_grapheme


logger = logging.getLogger(__name__)

THREAD_MAINTENANCE_TASK = "thread.maintenance"
THREAD_INACTIVITY_DISPATCH_TASK = "thread.inactivity.dispatch"
THREAD_MAINTENANCE_BACKFILL_TASK = "thread.maintenance.backfill_sweep"
THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID = "thread:maintenance-backfill"

_STALE_THREAD_RELATED_TASKS = (
	CHAT_SUMMARIZE_MESSAGES_TASK,
	CHAT_CONDENSE_SUMMARIES_TASK,
	MEMORY_POST_PROCESSING_TASK,
	THREAD_MAINTENANCE_TASK,
)

PASSAGE_ENRICHMENT_PIPELINE_VERSION = 1


@async_shared_broker.task(task_name=THREAD_INACTIVITY_DISPATCH_TASK)
async def dispatch_thread_inactivity_maintenance(
	thread_id: str,
	observed_last_activity_at: str,
) -> int:
	return await dispatch_due_thread_inactivity_maintenance(
		thread_id,
		observed_last_activity_at,
	)


@async_shared_broker.task(task_name=THREAD_MAINTENANCE_BACKFILL_TASK)
async def dispatch_thread_maintenance_backfill_sweep() -> JSONObject:
	return await run_thread_maintenance_backfill_sweep(respect_enabled=True)


def _thread_maintenance_inactivity_hours() -> int:
	return settings.tasks.thread_maintenance.inactivity_hours


def _thread_maintenance_queued_supersede_after() -> timedelta:
	return timedelta(
		minutes=settings.tasks.thread_maintenance.queued_supersede_after_minutes
	)


def _thread_maintenance_active_supersede_after() -> timedelta:
	return timedelta(
		minutes=settings.tasks.thread_maintenance.active_supersede_after_minutes
	)


def _thread_stale_task_cleanup_after() -> timedelta:
	return timedelta(
		minutes=settings.tasks.thread_maintenance.stale_task_cleanup_after_minutes
	)


def _thread_inactivity_schedule_id(thread_id: TypeID) -> str:
	return f"thread:inactivity-maintenance:{thread_id}"


def _ceil_to_minute(value: datetime) -> datetime:
	if value.second == 0 and value.microsecond == 0:
		return value
	return value.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _ensure_aware_utc(value: datetime) -> datetime:
	if value.tzinfo is None:
		return value.replace(tzinfo=UTC)
	return value.astimezone(UTC)


def _task_last_event_at(task: Task) -> datetime | None:
	last_event_at = task.last_event_at or task.updated_at or task.created_at
	if last_event_at is None:
		return None
	return _ensure_aware_utc(last_event_at)


def _active_task_is_stale(task: Task, stale_after: timedelta) -> bool:
	last_event_at = _task_last_event_at(task)
	if last_event_at is None:
		return False
	return datetime.now(tz=UTC) - last_event_at > stale_after


def _active_queued_task_is_stale(task: Task, stale_after: timedelta) -> bool:
	if (task.progress or 0) != 0:
		return False
	if not (task.stage or "").lower().startswith("queued"):
		return False
	last_event_at = _task_last_event_at(task)
	if last_event_at is None:
		return False
	return datetime.now(tz=UTC) - last_event_at > stale_after


async def start_thread_maintenance_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	observed_last_activity_at: datetime | None = None,
	replace_metadata: bool = False,
	origin_session_id: str | None = None,
	stage: str = "queued",
	source: str = "direct",
	reason: str = "requested",
) -> Task:
	"""enqueue durable metadata/summary maintenance for one thread."""
	metadata: JSONObject = {
		"thread_id": str(thread_id),
		"replace_metadata": replace_metadata,
		"maintenance_source": source,
		"maintenance_reason": reason,
	}
	if observed_last_activity_at is not None:
		metadata["observed_last_activity_at"] = observed_last_activity_at.isoformat()
		if reason != "mandatory_metadata":
			metadata["inactivity_hours"] = _thread_maintenance_inactivity_hours()
	if origin_session_id is not None:
		metadata["origin_session_id"] = origin_session_id
	existing = await find_active_task(
		session, THREAD_MAINTENANCE_TASK, {"thread_id": str(thread_id)}
	)
	if existing is not None:
		queued_stale = _active_queued_task_is_stale(
			existing, _thread_maintenance_queued_supersede_after()
		)
		if not queued_stale and not _active_task_is_stale(
			existing, _thread_maintenance_active_supersede_after()
		):
			logger.info(
				"thread maintenance enqueue skipped; active task exists "
				"thread_id=%s existing_task_id=%s user_id=%s source=%s reason=%s",
				thread_id,
				existing.id,
				principal.user.id,
				source,
				reason,
			)
			return existing
		failure_result: JSONObject
		if queued_stale:
			logger.warning(
				"thread maintenance queued task is stale; superseding "
				"thread_id=%s queued_task_id=%s user_id=%s source=%s reason=%s",
				thread_id,
				existing.id,
				principal.user.id,
				source,
				reason,
			)
			failure_stage = "queued task superseded"
			failure_result = {
				"error": "stale_queued_task",
				"message": "superseded after queued inactivity",
				"thread_id": str(thread_id),
			}
		else:
			logger.warning(
				"thread maintenance active task is stale; superseding "
				"thread_id=%s stale_task_id=%s user_id=%s source=%s reason=%s",
				thread_id,
				existing.id,
				principal.user.id,
				source,
				reason,
			)
			failure_stage = "stale task superseded"
			failure_result = {
				"error": "stale_active_task",
				"message": "superseded by a new thread maintenance task",
				"thread_id": str(thread_id),
			}
		await update_task_execution(
			existing.id,
			status_value=TaskStatus.FAILED,
			stage=failure_stage,
			result=failure_result,
		)
	logger.info(
		"thread maintenance enqueue requested thread_id=%s user_id=%s "
		"source=%s reason=%s stage=%s replace_metadata=%s observed_last_activity_at=%s",
		thread_id,
		principal.user.id,
		source,
		reason,
		stage,
		replace_metadata,
		observed_last_activity_at.isoformat()
		if observed_last_activity_at is not None
		else None,
	)
	return await start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=THREAD_MAINTENANCE_TASK,
		metadata=metadata,
		stage=stage,
		progress=0,
		spawned_thread_id=thread_id,
	)


async def start_thread_inactivity_maintenance_task(
	session: AsyncSession,
	principal: Principal,
	thread: Thread,
	source: str = "inactivity_timer",
	reason: str = "inactivity_timer",
) -> Task:
	"""enqueue maintenance for one inactive thread observed by the timer."""
	return await start_thread_maintenance_task(
		session,
		principal,
		thread.id,
		observed_last_activity_at=thread.last_activity_at,
		source=source,
		reason=reason,
	)


async def schedule_thread_inactivity_maintenance(
	thread_id: TypeID,
	session: AsyncSession | None = None,
	source: str = "post_run",
) -> bool:
	"""start mandatory work now or reset the deferred inactivity timer."""
	if boot_settings.TESTING:
		return False
	schedule_id = _thread_inactivity_schedule_id(thread_id)
	await redis_schedule_source.delete_schedule(schedule_id)

	async def schedule_with(active_session: AsyncSession) -> bool:
		thread = await active_session.get(Thread, thread_id)
		if thread is None:
			return False
		await active_session.refresh(thread)
		if thread.last_activity_at is None or thread.is_temporary:
			return False
		if thread_needs_mandatory_maintenance(thread):
			principal = await load_principal_for_user(thread.owner_id, active_session)
			await start_thread_maintenance_task(
				active_session,
				principal,
				thread.id,
				observed_last_activity_at=thread.last_activity_at,
				stage="queued mandatory metadata",
				source=source,
				reason="mandatory_metadata",
			)
			return True
		if not await thread_needs_deferred_maintenance(thread, active_session):
			return False
		last_activity_at = _ensure_aware_utc(thread.last_activity_at)
		due_at = last_activity_at + timedelta(
			hours=_thread_maintenance_inactivity_hours()
		)
		if due_at <= datetime.now(tz=UTC):
			return False
		await (
			dispatch_thread_inactivity_maintenance.kicker()
			.with_schedule_id(schedule_id)
			.schedule_by_time(
				redis_schedule_source,
				_ceil_to_minute(due_at),
				str(thread.id),
				last_activity_at.isoformat(),
			)
		)
		logger.info(
			"thread inactivity maintenance timer scheduled thread_id=%s "
			"schedule_id=%s source=%s due_at=%s observed_last_activity_at=%s",
			thread.id,
			schedule_id,
			source,
			_ceil_to_minute(due_at).isoformat(),
			last_activity_at.isoformat(),
		)
		return True

	if session is not None:
		return await schedule_with(session)
	async with async_session_local() as new_session:
		return await schedule_with(new_session)


async def dispatch_due_thread_inactivity_maintenance(
	thread_id: str,
	observed_last_activity_at: str,
) -> int:
	"""enqueue maintenance when a one-shot inactivity timer matures."""
	try:
		observed_at = datetime.fromisoformat(observed_last_activity_at)
	except ValueError:
		return 0
	observed_at = _ensure_aware_utc(observed_at)
	if datetime.now(tz=UTC) < observed_at + timedelta(
		hours=_thread_maintenance_inactivity_hours()
	):
		return 0
	async with async_session_local() as session:
		thread = await session.get(Thread, TypeID(thread_id))
		if thread is None or thread.last_activity_at is None:
			return 0
		last_activity_at = _ensure_aware_utc(thread.last_activity_at)
		if last_activity_at != observed_at:
			await schedule_thread_inactivity_maintenance(thread.id, session)
			return 0
		needs_mandatory = thread_needs_mandatory_maintenance(thread)
		needs_deferred = await thread_needs_deferred_maintenance(thread, session)
		if not needs_mandatory and not needs_deferred:
			return 0
		metadata: JSONObject = {"thread_id": str(thread.id)}
		if (
			await find_active_task(session, THREAD_MAINTENANCE_TASK, metadata)
			is not None
		):
			return 0
		principal = await load_principal_for_user(thread.owner_id, session)
		await start_thread_inactivity_maintenance_task(session, principal, thread)
		return 1


async def schedule_post_run_thread_upkeep(
	thread_id: TypeID,
	session: AsyncSession | None = None,
) -> bool:
	"""schedule asynchronous upkeep after a completed run."""
	if boot_settings.TESTING:
		return False

	async def upkeep_with(active_session: AsyncSession) -> bool:
		thread = await active_session.get(Thread, thread_id)
		if thread is None or thread.is_temporary:
			return False
		if not thread_needs_mandatory_maintenance(thread):
			await schedule_thread_content_vectorization(thread_id)
		return await schedule_thread_inactivity_maintenance(
			thread_id, active_session, source="post_run"
		)

	if session is not None:
		return await upkeep_with(session)
	async with async_session_local() as new_session:
		return await upkeep_with(new_session)


async def delete_thread_inactivity_maintenance_schedule(thread_id: TypeID) -> None:
	"""delete the inactivity timer for a thread."""
	if boot_settings.TESTING:
		return
	await redis_schedule_source.delete_schedule(
		_thread_inactivity_schedule_id(thread_id)
	)


async def fail_stale_thread_related_tasks() -> int:
	"""fail old active model-backed tasks before they block new attempts."""
	return await fail_stale_active_tasks(
		_STALE_THREAD_RELATED_TASKS,
		_thread_stale_task_cleanup_after(),
		"thread-related task stopped reporting progress",
	)


async def run_thread_maintenance_backfill_sweep(
	batch_size: int | None = None,
	max_lookback_days: int | None = None,
	min_inactivity_hours: int | None = None,
	respect_enabled: bool = True,
) -> JSONObject:
	"""dispatch maintenance for stale threads in one bounded batch."""
	if respect_enabled:
		settings.reload()
	backfill_settings = settings.tasks.maintenance_backfill
	if respect_enabled and not backfill_settings.enabled:
		logger.info(
			"thread maintenance backfill sweep skipped reason=disabled "
			"respect_enabled=%s schedule_id=%s",
			respect_enabled,
			THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID,
		)
		return {"skipped": True, "reason": "disabled", "dispatched": 0}

	effective_batch = (
		batch_size if batch_size is not None else backfill_settings.batch_size
	)
	effective_lookback = (
		max_lookback_days
		if max_lookback_days is not None
		else backfill_settings.max_lookback_days
	)
	effective_inactivity = (
		min_inactivity_hours
		if min_inactivity_hours is not None
		else backfill_settings.min_inactivity_hours
	)
	if effective_batch <= 0 or effective_lookback <= 0 or effective_inactivity <= 0:
		logger.warning(
			"thread maintenance backfill sweep skipped reason=invalid_bounds "
			"batch_size=%d lookback_days=%d min_inactivity_hours=%d",
			effective_batch,
			effective_lookback,
			effective_inactivity,
		)
		return {"skipped": True, "reason": "invalid_bounds", "dispatched": 0}

	now = datetime.now(tz=UTC)
	inactive_before = now - timedelta(hours=effective_inactivity)
	inactive_since = now - timedelta(days=effective_lookback)
	dispatched = 0
	skipped_existing = 0
	dispatched_thread_ids: list[JSONValue] = []
	vectors_dispatched = 0
	state_payloads_synced = 0
	async with async_session_local() as session:
		threads = await list_threads_due_for_maintenance(
			session,
			inactive_before=inactive_before,
			inactive_since=inactive_since,
			limit=effective_batch,
		)
		for thread in threads:
			metadata: JSONObject = {"thread_id": str(thread.id)}
			existing = await find_active_task(
				session, THREAD_MAINTENANCE_TASK, metadata
			)
			if existing is not None:
				logger.info(
					"thread maintenance backfill skipped active task "
					"thread_id=%s task_id=%s",
					thread.id,
					existing.id,
				)
				skipped_existing += 1
				continue
			principal = await load_principal_for_user(thread.owner_id, session)
			await start_thread_inactivity_maintenance_task(
				session,
				principal,
				thread,
				source="backfill_sweep",
				reason="backfill_sweep",
			)
			dispatched += 1
			dispatched_thread_ids.append(str(thread.id))

		vector_ids: list[str] = []
		if settings.assets.thread_passages.enabled:
			collection = await get_collection(session)
			vector_stmt = (
				select(Thread.id)
				.where(
					Thread.deleted_at.is_(None),
					Thread.is_temporary.is_(False),
					content_vectors_due_predicate(collection),
				)
				.order_by(Thread.last_activity_at.desc().nulls_last())
				.limit(effective_batch)
			)
			if dispatched_thread_ids:
				vector_stmt = vector_stmt.where(
					Thread.id.notin_([str(tid) for tid in dispatched_thread_ids])
				)
			vector_ids = [str(row[0]) for row in (await session.execute(vector_stmt))]

		state_stmt = (
			select(Thread.id)
			.where(
				Thread.deleted_at.is_(None),
				Thread.is_temporary.is_(False),
				state_vectors_due_predicate(),
			)
			.order_by(Thread.last_activity_at.desc().nulls_last())
			.limit(effective_batch)
		)
		state_ids = [str(row[0]) for row in (await session.execute(state_stmt))]
		if state_ids:
			await sync_thread_state_vectors(session, state_ids)
			state_payloads_synced = len(state_ids)
	for thread_id in vector_ids:
		await schedule_thread_content_vectorization(TypeID(thread_id))
		vectors_dispatched += 1

	logger.info(
		"thread maintenance backfill swept threads=%d"
		" dispatched=%d skipped_existing=%d vectors_dispatched=%d"
		" state_payloads_synced=%d",
		len(dispatched_thread_ids) + skipped_existing,
		dispatched,
		skipped_existing,
		vectors_dispatched,
		state_payloads_synced,
	)
	return {
		"dispatched": dispatched,
		"skipped_existing": skipped_existing,
		"vectors_dispatched": vectors_dispatched,
		"state_payloads_synced": state_payloads_synced,
		"batch_size": effective_batch,
		"max_lookback_days": effective_lookback,
		"min_inactivity_hours": effective_inactivity,
		"dispatched_thread_ids": dispatched_thread_ids,
	}


async def reconcile_thread_maintenance_backfill_schedule() -> bool:
	"""install or remove the backfill cron schedule based on settings."""
	if boot_settings.TESTING:
		return False
	settings.reload()
	await redis_schedule_source.delete_schedule(THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID)
	backfill_settings = settings.tasks.maintenance_backfill
	if not backfill_settings.enabled:
		logger.info("thread maintenance backfill schedule cleared (disabled)")
		return False
	try:
		await (
			dispatch_thread_maintenance_backfill_sweep.kicker()
			.with_schedule_id(THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID)
			.schedule_by_cron(
				redis_schedule_source,
				backfill_settings.cron,
			)
		)
	except ValueError as exc:
		logger.warning(
			"thread maintenance backfill cron rejected by taskiq: %s (cron=%r)",
			exc,
			backfill_settings.cron,
		)
		return False
	logger.info(
		"thread maintenance backfill schedule installed"
		" cron=%r batch_size=%d lookback_days=%d",
		backfill_settings.cron,
		backfill_settings.batch_size,
		backfill_settings.max_lookback_days,
	)
	return True


async def clear_disabled_thread_maintenance_backfill_schedule() -> bool:
	"""remove any persisted backfill schedule before TaskIQ startup when disabled."""
	if boot_settings.TESTING:
		return False
	settings.reload()
	if settings.tasks.maintenance_backfill.enabled:
		return False
	await redis_schedule_source.delete_schedule(THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID)
	logger.info(
		"thread maintenance backfill schedule cleared before taskiq startup "
		"reason=disabled schedule_id=%s",
		THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID,
	)
	return True


on_settings_reload(reconcile_thread_maintenance_backfill_schedule)


_MAINTENANCE_PROMPT = """\
given the active chat history, generate compact catalog metadata for finding and
recognizing this thread later.

this metadata will be used for vector search and standard keyword searches.

the summary is a search/catalog snippet, not a transcript recap. write 1-2
sentences that synthesize the durable point of the chat: the user's intent, the
final outcome or artifact, important decisions, named entities, files, URLs,
failures that still matter, and unresolved follow-up. do not retell each turn,
list tool calls, quote raw errors unless the error is the durable outcome, or
repeat "user asked / assistant answered" for every exchange. if the chat is
mostly exploratory, name the topic and conclusion instead of narrating steps.
"""

_SUMMARY_FIELD_DESCRIPTION = """\
1-2 sentence catalog snippet, not a chronological recap. capture the
durable request, outcome/artifact, named entities, decisions, failures,
and unresolved work in a compact searchable form
"""


class _ThreadMaintenanceOut(BaseModel):
	"""structured output schema for thread maintenance."""

	title: str = Field(
		max_length=50,
		description=(
			"1-3 lowercase words that identify this exact chat;"
			"avoid generic topic titles when a more specific artifact or task exists"
		),
		examples=["login debug", "tunnel essay"],
	)
	tags: list[str] = Field(
		min_length=1,
		max_length=6,
		description=(
			"short lowercase catalog tags for search and filtering; prefer concrete "
			"entities, workflows, artifacts, and domains mentioned in the chat"
		),
		examples=[["auth", "debugging", "oauth"], ["essay", "physics"]],
	)
	summary: str = Field(
		min_length=1,
		description=_SUMMARY_FIELD_DESCRIPTION,
		examples=[
			(
				"debugged an oauth login loop caused by a callback mismatch; redirect "
				"URI updates were identified and verification was left pending."
			)
		],
	)
	emoji: Annotated[str, AfterValidator(validate_single_grapheme)] = Field(
		description="one single emoji that visually identifies the thread",
		examples=["🔐", "📝"],
	)

	def display_title(self) -> str:
		title = self.title.strip().lower()
		emoji = self.emoji.strip()
		return f"{emoji} {title}".strip()


_PASSAGE_ENRICHMENT_PROMPT = """\
given a chat's title, catalog summary, neighboring transcript passages, and one
target passage, write 1-2 sentences of search context for the target passage.

name the topic under discussion, resolve pronouns and vague referents to the
concrete entities they point at, and name the decisions or artifacts in play.
the context is prepended to the passage for search indexing, so make every
word a useful retrieval term. do not recap turn by turn or evaluate quality.
"""


class _PassageEnrichmentOut(BaseModel):
	"""structured output schema for passage enrichment."""

	context: str = Field(
		min_length=1,
		description="1-2 sentence search context situating the target passage",
	)


async def enrich_thread_passages(
	thread_id: TypeID,
	session: AsyncSession,
) -> int:
	"""generate search context for stored passages that lack it.

	newest passages first, bounded per run by settings. generated context is
	applied through reconcile so enriched passages re-embed with it and keep
	it across future reconciles. returns the number of passages enriched.
	"""
	passage_settings = settings.assets.thread_passages
	cfg = passage_settings.enrichment
	if not passage_settings.enabled or not cfg.enabled:
		return 0
	thread = await session.get(Thread, thread_id)
	if thread is None or _maintenance_head_id(thread) is None:
		return 0
	targets = await list_unenriched_passages(thread.id, session, cfg.max_per_run)
	if not targets:
		return 0
	message_result = await session.execute(
		select(Message).where(Message.thread_id == thread.id)
	)
	messages = list(message_result.scalars().all())
	target_tokens, overlap_tokens = await passage_generation_params(session)
	planned = build_transcript_passages(
		messages,
		target_tokens=target_tokens,
		overlap_tokens=overlap_tokens,
	)
	planned_by_key = {_transcript_passage_key(passage): passage for passage in planned}
	planned_indices = {
		_transcript_passage_key(passage): index for index, passage in enumerate(planned)
	}

	summary = latest_active_summary_text(thread, SummaryPurpose.CATALOG) or ""
	chat_model = await resolve_task_chat_model(session, "passage_enrichment")
	model_id = (
		settings.ai.tasks.passage_enrichment_model_id
		or settings.ai.tasks.default_model_id
	)
	enriched = 0
	for passage in targets:
		key = _stored_passage_key(passage)
		planned_passage = planned_by_key.get(key)
		index = planned_indices.get(key)
		if planned_passage is None or index is None:
			continue
		before = planned[max(index - cfg.lookbehind, 0) : index]
		after = planned[index + 1 : index + 1 + cfg.lookahead]
		parts = [f"chat title: {thread.title or '(untitled)'}"]
		if summary:
			parts.append(f"catalog summary: {summary}")
		if before:
			parts.append(
				"preceding passages:\n" + "\n---\n".join(item.text for item in before)
			)
		if after:
			parts.append(
				"following passages:\n" + "\n---\n".join(item.text for item in after)
			)
		parts.append(f"target passage:\n{planned_passage.text}")
		passage_enrichment_prompt = settings.ai.tasks.passage_enrichment_prompt
		structured = await run_chat_model_json_schema(
			chat_model,
			thread=SDKThread(
				messages=[
					SDKSystemMessage.from_text(
						passage_enrichment_prompt
						if passage_enrichment_prompt is not None
						else _PASSAGE_ENRICHMENT_PROMPT
					),
					SDKUserMessage.from_text("\n\n".join(parts)),
				]
			),
			json_schema=_PassageEnrichmentOut.model_json_schema(),
			purpose="passage_enrichment",
		)
		out = _PassageEnrichmentOut.model_validate(structured)
		context = out.context.strip()
		if context:
			passage.enrichment = context
			passage.enrichment_model_id = TypeID(model_id) if model_id else None
			passage.enriched_at = datetime.now(tz=UTC)
			passage.enrichment_pipeline_v = PASSAGE_ENRICHMENT_PIPELINE_VERSION
			enriched += 1
	if not enriched:
		return 0
	await reconcile_thread_content_vectors(session, thread_ids=[thread_id])
	return enriched


def _stored_passage_key(passage: ThreadPassage) -> tuple[str, str, int]:
	return (
		str(passage.first_message_id),
		str(passage.last_message_id),
		passage.part_index,
	)


def _transcript_passage_key(passage: TranscriptPassage) -> tuple[str, str, int]:
	return (
		passage.first_message_id,
		passage.last_message_id,
		passage.part_index,
	)


def _maintenance_head_id(thread: Thread) -> TypeID | None:
	"""return the eligible thread's current message."""
	if thread.deleted_at is not None or thread.is_temporary:
		return None
	return thread.current_message_id


def _latest_branch_update(messages: list[Message]) -> datetime | None:
	"""return the newest create/update timestamp in a branch."""
	latest: datetime | None = None
	for message in messages:
		candidate = message.updated_at or message.created_at
		if latest is None or candidate > latest:
			latest = candidate
	return latest


def _summary_covers_branch(
	summary: ThreadSummary,
	head_id: TypeID,
	latest_branch_update: datetime | None,
) -> bool:
	"""return whether a catalog summary still covers the active branch."""
	if not summary.content.strip():
		return False
	if summary.end_message_id != head_id:
		return False
	if latest_branch_update is not None and summary.created_at < latest_branch_update:
		return False
	return True


def thread_metadata_missing(thread: Thread) -> bool:
	"""whether mandatory thread title or tags still need to be generated."""
	return (thread.title or "").strip() == "" or not thread.tags


async def _thread_summary_stale(
	thread: Thread,
	head_id: TypeID,
	session: AsyncSession,
) -> bool:
	"""return whether the thread's active branch lacks a fresh catalog summary."""
	branch = await walk_message_branch(
		session,
		thread.id,
		head_id,
	)
	latest_branch_update = _latest_branch_update(branch)
	summaries = await list_active_summaries(
		thread.id,
		session,
		purpose=SummaryPurpose.CATALOG,
	)
	return not any(
		_summary_covers_branch(summary, head_id, latest_branch_update)
		for summary in summaries
	)


def thread_needs_mandatory_maintenance(thread: Thread) -> bool:
	"""whether missing required catalog metadata should be generated now."""
	return _maintenance_head_id(thread) is not None and thread_metadata_missing(thread)


async def thread_needs_deferred_maintenance(
	thread: Thread,
	session: AsyncSession,
) -> bool:
	"""whether summary-only work should wait for the inactivity timer."""
	head_id = _maintenance_head_id(thread)
	if head_id is None:
		return False
	if thread_metadata_missing(thread):
		return False
	return await _thread_summary_stale(thread, head_id, session)


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

	results are ordered oldest-first and SQL-limited before running the
	maintenance predicate so each sweep inspects at most one configured batch.
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
	update_activity: bool = True,
) -> JSONObject:
	"""generate missing metadata and a fresh active-branch summary if needed."""
	thread = await session.get(Thread, thread_id)
	if thread is None or thread.deleted_at is not None or thread.is_temporary:
		return {"thread_id": str(thread_id), "skipped": True, "reason": "not eligible"}
	head_id = _maintenance_head_id(thread)
	if head_id is None:
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
	summaries = await list_active_summaries(
		thread_id,
		session,
		purpose=SummaryPurpose.CATALOG,
	)
	metadata_needed = replace_metadata or thread_metadata_missing(thread)
	summary_needed = not any(
		_summary_covers_branch(summary, head_id, latest_branch_update)
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
		summary.end_message_id == head_id
		and not _summary_covers_branch(summary, head_id, latest_branch_update)
		for summary in summaries
	)
	if not ignore_existing_summaries:
		sdk_thread = (
			await apply_context_compaction(
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
	maintenance_prompt = settings.ai.tasks.thread_maintenance_prompt
	structured = await run_chat_model_json_schema(
		chat_model,
		thread=SDKThread(
			messages=[
				SDKSystemMessage.from_text(
					maintenance_prompt
					if maintenance_prompt is not None
					else _MAINTENANCE_PROMPT
				),
				SDKUserMessage.from_text("\n".join(transcript_lines)),
			]
		),
		json_schema=_ThreadMaintenanceOut.model_json_schema(),
		purpose="thread_maintenance",
	)
	out = _ThreadMaintenanceOut.model_validate(structured)

	updated_metadata = False
	if metadata_needed:
		update_fields: dict[str, object] = {}
		desired_title = out.display_title() or None
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
				update_activity=update_activity,
			)
			updated_metadata = True

	summary_id: TypeID | None = None
	if summary_needed:
		summary = await create_summary(
			thread_id=thread_id,
			purpose=SummaryPurpose.CATALOG,
			content=out.summary.strip(),
			message_count=len(branch),
			start_message_id=branch[0].id,
			end_message_id=TypeID(thread.current_message_id),
			session=session,
		)
		summary_id = summary.id
		await supersede_summaries(
			[summary.id for summary in summaries if summary.id != summary_id],
			summary_id,
			session,
		)
		await session.refresh(thread, attribute_names=["messages", "summaries"])
		await vectorize_resource(
			spec=THREAD_SPEC,
			resource=thread,
			session=session,
			extra_metadata=(
				await fetch_bulk_acl_metadata(
					[str(thread.id)], ResourceType.THREAD, session
				)
			)[str(thread.id)],
		)

	await reconcile_thread_content_vectors(session, thread_ids=[thread_id])
	enriched = 0
	try:
		enriched = await enrich_thread_passages(thread_id, session)
	except Exception:
		# enrichment is an optional quality upgrade; the sweep or the next
		# maintenance run retries the still-unenriched passages.
		logger.exception("passage enrichment failed thread_id=%s", thread_id)

	return {
		"thread_id": str(thread_id),
		"metadata_updated": updated_metadata,
		"summary_id": str(summary_id) if summary_id is not None else None,
		"summary_updated": summary_id is not None,
		"passages_enriched": enriched,
	}
