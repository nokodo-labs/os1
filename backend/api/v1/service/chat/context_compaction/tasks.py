"""Durable task starters for context compaction."""

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.task import Task, TaskType
from api.v1.service.authentication import Principal
from api.v1.service.tasks import find_active_task, start_task
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


CHAT_SUMMARIZE_MESSAGES_TASK = "chat.summarize_messages"
CHAT_CONDENSE_SUMMARIES_TASK = "chat.condense_summaries"


async def start_summarize_messages_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	start_message_id: TypeID,
	end_message_id: TypeID,
	branch_head_message_id: str | None = None,
) -> Task:
	"""enqueue durable summarization for a persisted thread message range."""
	metadata: JSONObject = {
		"thread_id": str(thread_id),
		"purpose": "agent_context",
		"start_message_id": str(start_message_id),
		"end_message_id": str(end_message_id),
	}
	if branch_head_message_id is not None:
		metadata["branch_head_message_id"] = branch_head_message_id
	existing = await find_active_task(session, CHAT_SUMMARIZE_MESSAGES_TASK, metadata)
	if existing is not None:
		return existing
	return await start_task(
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
	branch_head_message_id: str | None = None,
) -> Task:
	"""enqueue durable summary condensation for one thread."""
	metadata: JSONObject = {"thread_id": str(thread_id)}
	if branch_head_message_id is not None:
		metadata["branch_head_message_id"] = branch_head_message_id
	existing = await find_active_task(session, CHAT_CONDENSE_SUMMARIES_TASK, metadata)
	if existing is not None:
		return existing
	return await start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=CHAT_CONDENSE_SUMMARIES_TASK,
		metadata=metadata,
		stage="queued condensation",
		progress=0,
		spawned_thread_id=thread_id,
	)
