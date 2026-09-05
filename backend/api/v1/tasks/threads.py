"""TaskIQ entrypoints for durable thread-related work."""

from datetime import UTC, datetime

from api.database import async_session_local
from api.models.thread import Thread
from api.settings import settings
from api.v1.service.activities import start_activity
from api.v1.service.authentication import load_principal_for_user
from api.v1.service.chat.context_compaction.summarization import (
	SummaryRangeStaleError,
	condense_summaries,
	summarize_thread_message_range,
)
from api.v1.service.chat.context_compaction.tasks import (
	CHAT_CONDENSE_SUMMARIES_TASK,
	CHAT_SUMMARIZE_MESSAGES_TASK,
)
from api.v1.service.chat.message_references import wait_message_reference
from api.v1.service.chat.thread_maintenance import (
	THREAD_MAINTENANCE_TASK,
	maintain_thread_metadata,
)
from api.v1.service.events import build_live_persisting_event_emitter
from api.v1.service.memories import (
	MEMORY_POST_PROCESSING_TASK,
	post_process_relevant_memories,
)
from api.v1.service.tasks import (
	TaskContext,
	register_task_runner,
)
from api.v1.service.threads.vectorization import run_thread_content_vectorization
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


_registered_shared_tasks = (run_thread_content_vectorization,)


def _thread_task_runner_timeout_seconds() -> float:
	return float(settings.tasks.thread_maintenance.runner_timeout_seconds)


@register_task_runner(
	CHAT_SUMMARIZE_MESSAGES_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_summarize_messages_task(context: TaskContext) -> JSONObject:
	"""run persisted message-range summarization."""
	thread_id_value = context.metadata.get("thread_id")
	start_value = context.metadata.get("start_message_id")
	end_value = context.metadata.get("end_message_id")
	branch_head_value = context.metadata.get("branch_head_message_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	if not isinstance(start_value, str) or not start_value:
		raise ValueError("start_message_id metadata is required")
	if not isinstance(end_value, str) or not end_value:
		raise ValueError("end_message_id metadata is required")
	branch_head_message_id = (
		TypeID(branch_head_value)
		if isinstance(branch_head_value, str) and branch_head_value
		else None
	)

	thread_id = TypeID(thread_id_value)
	await context.update(progress=10, stage="loading messages")
	async with async_session_local() as session:
		try:
			summary_id = await summarize_thread_message_range(
				thread_id=thread_id,
				start_message_id=TypeID(start_value),
				end_message_id=TypeID(end_value),
				branch_head_message_id=branch_head_message_id,
				session=session,
			)
		except SummaryRangeStaleError as exc:
			await context.update(progress=90, stage="summary range stale")
			return {
				"thread_id": str(thread_id),
				"summary_id": None,
				"skipped": True,
				"reason": str(exc),
			}
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	return {"thread_id": str(thread_id), "summary_id": str(summary_id)}


@register_task_runner(
	CHAT_CONDENSE_SUMMARIES_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_condense_summaries_task(context: TaskContext) -> JSONObject:
	"""run summary condensation for one thread."""
	thread_id_value = context.metadata.get("thread_id")
	branch_head_value = context.metadata.get("branch_head_message_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	thread_id = TypeID(thread_id_value)
	branch_head_message_id = (
		TypeID(branch_head_value)
		if isinstance(branch_head_value, str) and branch_head_value
		else None
	)
	await context.update(progress=10, stage="loading summaries")
	async with async_session_local() as session:
		try:
			summary_id = await condense_summaries(
				thread_id=thread_id,
				expected_branch_head_message_id=branch_head_message_id,
				session=session,
			)
		except SummaryRangeStaleError as exc:
			await context.update(progress=90, stage="condensation range stale")
			return {
				"thread_id": str(thread_id),
				"summary_id": None,
				"skipped": True,
				"reason": str(exc),
			}
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	return {
		"thread_id": str(thread_id),
		"summary_id": str(summary_id) if summary_id is not None else None,
		"skipped": summary_id is None,
	}


@register_task_runner(
	MEMORY_POST_PROCESSING_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_memory_post_processing_task(
	context: TaskContext,
) -> JSONObject:
	"""run memory maintenance for the owning user."""
	query_text = context.runtime.get("query_text")
	max_related_memories = context.runtime.get("max_related_memories")
	if not isinstance(query_text, str) or not query_text.strip():
		return {"skipped": True, "reason": "empty query"}
	if not isinstance(max_related_memories, int) or max_related_memories <= 0:
		max_related_memories = 10

	snapshot = context.runtime.get("conversation_snapshot")
	conversation_snapshot = snapshot if isinstance(snapshot, str) else None
	thread_id_value = context.runtime.get("thread_id")
	thread_id = thread_id_value if isinstance(thread_id_value, str) else None
	message_id_value = context.runtime.get("message_id")
	message_id = message_id_value if isinstance(message_id_value, str) else None
	message_ref_value = context.runtime.get("message_ref")
	message_ref = message_ref_value if isinstance(message_ref_value, str) else None
	run_id_value = context.runtime.get("run_id")
	run_id = run_id_value if isinstance(run_id_value, str) else None
	emit_activity = context.runtime.get("emit_activity") is True

	async def report_progress(progress: int, stage: str) -> None:
		await context.update(progress=progress, stage=stage)

	await context.update(progress=10, stage="starting memory processing")
	# resolve message_id before processing so newly created memories get
	# source_message_id set; wait_message_reference is a quick poll if the
	# message is already committed.
	if message_id is None and message_ref is not None:
		message_id = await wait_message_reference(message_ref)
	async with async_session_local() as session:
		principal = await load_principal_for_user(context.user_id, session)
		result = await post_process_relevant_memories(
			query_text,
			session,
			principal=principal,
			max_related_memories=max_related_memories,
			conversation_snapshot=conversation_snapshot,
			progress_callback=report_progress,
			source_message_id=message_id,
		)
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	if emit_activity:
		await _emit_memory_maintenance_activity(
			result,
			user_id=str(context.user_id),
			thread_id=thread_id,
			message_id=message_id,
			run_id=run_id,
		)
	return result


def _activity_count(result: JSONObject, key: str) -> int:
	"""read an integer count from a memory maintenance result."""
	value = result.get(key)
	return value if isinstance(value, int) and not isinstance(value, bool) else 0


async def _emit_memory_maintenance_activity(
	result: JSONObject,
	user_id: str,
	thread_id: str | None,
	message_id: str | None,
	run_id: str | None,
) -> None:
	"""emit a memory_maintenance run activity when memories were changed."""
	created = _activity_count(result, "created")
	updated = _activity_count(result, "updated")
	deleted = _activity_count(result, "deleted")
	changed_kinds = sum(1 for count in (created, updated, deleted) if count > 0)
	if created + updated + deleted <= 0:
		return
	if thread_id is None or message_id is None or run_id is None:
		return

	emit = build_live_persisting_event_emitter()
	activity = await start_activity(
		emit,
		user_id=user_id,
		thread_id=thread_id,
		run_id=run_id,
		activity_type="memory_maintenance",
		message_id=message_id,
		title="updating memory",
	)
	if activity is None:
		return
	if changed_kinds > 1:
		summary = "memories updated"
	elif created > 0:
		summary = "memory saved" if created == 1 else "memories saved"
	elif updated > 0:
		summary = "memory updated" if updated == 1 else "memories updated"
	else:
		summary = "memory removed" if deleted == 1 else "memories removed"
	await activity.ended(
		outcome="success",
		message=summary,
		data={
			"created": created,
			"updated": updated,
			"deleted": deleted,
		},
	)


@register_task_runner(
	THREAD_MAINTENANCE_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_thread_maintenance_task(context: TaskContext) -> JSONObject:
	"""run thread metadata and branch-summary maintenance."""
	thread_id_value = context.metadata.get("thread_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	thread_id = TypeID(thread_id_value)
	replace_metadata = context.metadata.get("replace_metadata") is True
	origin_session_value = context.metadata.get("origin_session_id")
	origin_session_id = (
		origin_session_value if isinstance(origin_session_value, str) else None
	)
	observed_value = context.metadata.get("observed_last_activity_at")
	observed_at: datetime | None = None
	if isinstance(observed_value, str) and observed_value:
		try:
			observed_at = datetime.fromisoformat(observed_value)
		except ValueError:
			observed_at = None
		if observed_at is not None and observed_at.tzinfo is None:
			observed_at = observed_at.replace(tzinfo=UTC)

	await context.check_cancelled()
	await context.update(progress=10, stage="checking")
	# live mandatory maintenance counts as activity; deferred/backfill does not
	maintenance_source = context.metadata.get("maintenance_source", "")
	update_activity = maintenance_source == "post_run"
	async with async_session_local() as session:
		thread = await session.get(Thread, thread_id)
		if thread is None:
			return {
				"thread_id": thread_id_value,
				"skipped": True,
				"reason": "not found",
			}
		principal = await load_principal_for_user(thread.owner_id, session)
		await context.update(progress=45, stage="generating")
		result = await maintain_thread_metadata(
			thread_id,
			session,
			principal=principal,
			observed_last_activity_at=observed_at,
			replace_metadata=replace_metadata,
			origin_session_id=origin_session_id,
			update_activity=update_activity,
		)
		await session.commit()
	await context.check_cancelled()
	await context.update(progress=90, stage="finalizing")
	return result
