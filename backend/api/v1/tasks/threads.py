"""TaskIQ wrappers for durable thread-related work."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_local
from api.models.task import Task, TaskType
from api.models.thread import Thread
from api.taskiq import broker
from api.v1.service import memories as memory_service
from api.v1.service import tasks as task_service
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, load_principal_for_user
from api.v1.service.chat.summarization import (
	condense_summaries,
	summarize_thread_message_range,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


CHAT_SUMMARIZE_MESSAGES_TASK = "chat.summarize_messages"
CHAT_CONDENSE_SUMMARIES_TASK = "chat.condense_summaries"
MEMORY_POST_PROCESSING_TASK = "memory.post_process"
THREAD_MAINTENANCE_TASK = "thread.maintenance"
THREAD_INACTIVITY_SWEEP_TASK = "thread.inactivity.sweep"
THREAD_INACTIVITY_HOURS = 8


async def start_summarize_messages_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	start_message_id: TypeID,
	end_message_id: TypeID,
) -> Task:
	"""enqueue durable summarization for a persisted thread message range."""
	metadata: JSONObject = {
		"thread_id": str(thread_id),
		"start_message_id": str(start_message_id),
		"end_message_id": str(end_message_id),
	}
	existing = await task_service.find_active_task(
		session, CHAT_SUMMARIZE_MESSAGES_TASK, metadata
	)
	if existing is not None:
		return existing
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=CHAT_SUMMARIZE_MESSAGES_TASK,
		metadata=metadata,
		stage="queued summarization",
		progress=0,
		spawned_thread_id=thread_id,
	)


async def start_condense_summaries_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
) -> Task:
	"""enqueue durable summary condensation for one thread."""
	metadata: JSONObject = {"thread_id": str(thread_id)}
	existing = await task_service.find_active_task(
		session, CHAT_CONDENSE_SUMMARIES_TASK, metadata
	)
	if existing is not None:
		return existing
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=CHAT_CONDENSE_SUMMARIES_TASK,
		metadata=metadata,
		stage="queued condensation",
		progress=0,
		spawned_thread_id=thread_id,
	)


async def start_memory_post_processing_task(
	session: AsyncSession,
	principal: Principal,
	query_text: str,
	max_related_memories: int,
) -> Task:
	"""enqueue durable memory maintenance for a conversation query."""
	runtime: JSONObject = {
		"query_text": query_text,
		"max_related_memories": max_related_memories,
	}
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=MEMORY_POST_PROCESSING_TASK,
		metadata={"query_length": len(query_text)},
		runtime=runtime,
		stage="queued memory processing",
		progress=0,
	)


async def start_thread_maintenance_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	observed_last_activity_at: datetime | None = None,
	replace_metadata: bool = False,
	origin_session_id: str | None = None,
	stage: str = "queued",
) -> Task:
	"""enqueue durable metadata/summary maintenance for one thread."""
	metadata: JSONObject = {
		"thread_id": str(thread_id),
		"replace_metadata": replace_metadata,
	}
	if observed_last_activity_at is not None:
		metadata["observed_last_activity_at"] = observed_last_activity_at.isoformat()
		metadata["inactivity_hours"] = THREAD_INACTIVITY_HOURS
	if origin_session_id is not None:
		metadata["origin_session_id"] = origin_session_id
	existing = await task_service.find_active_task(
		session, THREAD_MAINTENANCE_TASK, {"thread_id": str(thread_id)}
	)
	if existing is not None:
		return existing
	return await task_service.start_task(
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
) -> Task:
	"""enqueue maintenance for one inactive thread observed by the sweep."""
	return await start_thread_maintenance_task(
		session,
		principal,
		TypeID(thread.id),
		observed_last_activity_at=thread.last_activity_at,
	)


@task_service.register_task_runner(CHAT_SUMMARIZE_MESSAGES_TASK)
async def run_summarize_messages_task(context: task_service.TaskContext) -> JSONObject:
	"""run persisted message-range summarization."""
	thread_id_value = context.metadata.get("thread_id")
	start_value = context.metadata.get("start_message_id")
	end_value = context.metadata.get("end_message_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	if not isinstance(start_value, str) or not start_value:
		raise ValueError("start_message_id metadata is required")
	if not isinstance(end_value, str) or not end_value:
		raise ValueError("end_message_id metadata is required")

	thread_id = TypeID(thread_id_value)
	await context.update(progress=10, stage="loading messages")
	async with async_session_local() as session:
		summary_id = await summarize_thread_message_range(
			thread_id=thread_id,
			start_message_id=TypeID(start_value),
			end_message_id=TypeID(end_value),
			session=session,
		)
	await context.update(progress=90, stage="finalizing")
	return {"thread_id": str(thread_id), "summary_id": str(summary_id)}


@task_service.register_task_runner(CHAT_CONDENSE_SUMMARIES_TASK)
async def run_condense_summaries_task(context: task_service.TaskContext) -> JSONObject:
	"""run summary condensation for one thread."""
	thread_id_value = context.metadata.get("thread_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	thread_id = TypeID(thread_id_value)
	await context.update(progress=10, stage="loading summaries")
	async with async_session_local() as session:
		summary_id = await condense_summaries(thread_id=thread_id, session=session)
	await context.update(progress=90, stage="finalizing")
	return {
		"thread_id": str(thread_id),
		"summary_id": str(summary_id) if summary_id is not None else None,
		"skipped": summary_id is None,
	}


@task_service.register_task_runner(MEMORY_POST_PROCESSING_TASK)
async def run_memory_post_processing_task(
	context: task_service.TaskContext,
) -> JSONObject:
	"""run memory maintenance for the owning user."""
	query_text = context.runtime.get("query_text")
	max_related_memories = context.runtime.get("max_related_memories")
	if not isinstance(query_text, str) or not query_text.strip():
		return {"skipped": True, "reason": "empty query"}
	if not isinstance(max_related_memories, int) or max_related_memories <= 0:
		max_related_memories = 10

	await context.update(progress=10, stage="loading memories")
	async with async_session_local() as session:
		principal = await load_principal_for_user(context.user_id, session)
		result = await memory_service.post_process_relevant_memories(
			query_text,
			session,
			principal=principal,
			max_related_memories=max_related_memories,
		)
	await context.update(progress=90, stage="finalizing")
	return result


@task_service.register_task_runner(THREAD_MAINTENANCE_TASK)
async def run_thread_maintenance_task(context: task_service.TaskContext) -> JSONObject:
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
	async with async_session_local() as session:
		thread = await session.get(Thread, thread_id)
		if thread is None:
			return {
				"thread_id": thread_id_value,
				"skipped": True,
				"reason": "not found",
			}
		principal = await load_principal_for_user(TypeID(thread.owner_id), session)
		await context.update(progress=45, stage="generating")
		result = await thread_service.maintain_thread_metadata(
			thread_id,
			session,
			principal=principal,
			observed_last_activity_at=observed_at,
			replace_metadata=replace_metadata,
			origin_session_id=origin_session_id,
		)
	await context.check_cancelled()
	await context.update(progress=90, stage="finalizing")
	return result


@broker.task(
	task_name=THREAD_INACTIVITY_SWEEP_TASK,
	schedule=[{"cron": "*/15 * * * *"}],
)
async def dispatch_due_thread_inactivity_maintenance(limit: int = 50) -> int:
	"""enqueue maintenance for inactive threads with stale metadata or summaries."""
	cutoff = datetime.now(tz=UTC) - timedelta(hours=THREAD_INACTIVITY_HOURS)
	started = 0
	async with async_session_local() as session:
		threads = await thread_service.list_threads_due_for_maintenance(
			session,
			inactive_before=cutoff,
			limit=limit,
		)
		for thread in threads:
			metadata: JSONObject = {"thread_id": str(thread.id)}
			if (
				await task_service.find_active_task(
					session, THREAD_MAINTENANCE_TASK, metadata
				)
				is not None
			):
				continue
			principal = await load_principal_for_user(TypeID(thread.owner_id), session)
			await start_thread_inactivity_maintenance_task(
				session,
				principal,
				thread,
			)
			started += 1
	return started
