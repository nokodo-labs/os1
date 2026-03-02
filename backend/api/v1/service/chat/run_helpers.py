"""run helpers - sse formatting, threading, and broadcasting utilities.

extracted from agents.py to keep that module focused on
agent building and the main run_agent orchestration.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from api.database import AsyncSessionLocal
from api.models.agent import Agent as AgentORM
from api.models.event_types import EventType
from api.models.message import Message as MessageORM
from api.permissions import ResourceType
from api.schemas.runs import ClientContext
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import list_accessible_user_ids
from api.v1.service.events import event_connections
from api.v1.service.prompt_runtime import render_agent_instructions
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def safe_rollback(session: AsyncSession) -> None:
	"""rollback the session, swallowing errors if already closed."""
	try:
		await session.rollback()
	except Exception:
		pass


def sse_event(*, event: str, data: dict[str, object]) -> bytes:
	"""format an sse event (delegates to sse utils)."""
	return sse_encode(event=event, data=data)


def message_to_sse_data(msg: MessageORM) -> dict[str, object]:
	"""serialize a persisted orm message for sse streaming."""
	content_parts: list[dict[str, object]] = []
	for part in msg.content or []:
		if isinstance(part, dict):
			content_parts.append(part)
		else:
			content_parts.append({"type": "text", "text": str(part)})

	return {
		"id": str(msg.id),
		"thread_id": str(msg.thread_id),
		"parent_id": str(msg.parent_id) if msg.parent_id else None,
		"type": msg.type.value,
		"content": content_parts,
		"metadata_": msg.metadata_ or {},
		"sender_agent_id": str(msg.sender_agent_id) if msg.sender_agent_id else None,
		"sender_user_id": str(msg.sender_user_id) if msg.sender_user_id else None,
		"created_at": msg.created_at.isoformat() if msg.created_at else None,
	}


async def broadcast_run_event(
	*,
	thread_id: str,
	agent_id: str,
	run_id: str,
	started: bool,
) -> None:
	"""broadcast run.started / run.completed to all users with access to a thread."""
	msg_type = EventType.RUN_STARTED if started else EventType.RUN_COMPLETED
	payload: dict[str, object] = {
		"type": msg_type,
		"data": {
			"thread_id": thread_id,
			"agent_id": agent_id,
			"run_id": run_id,
		},
	}

	async with AsyncSessionLocal() as db_session:
		recipient_ids = await list_accessible_user_ids(
			ResourceType.THREAD, thread_id, db_session
		)

	if recipient_ids:
		await event_connections.send_to_users(recipient_ids, payload)


async def load_sdk_thread(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	parent_id: TypeID | None = None,
) -> tuple[SDKThread, TypeID | None]:
	"""load a thread's message branch and convert to an SDK thread.

	this is the single entry point for determining which messages from
	a thread are included in agent context. future windowing and
	history-summarization logic should be applied here.

	when parent_id is provided and differs from the thread's current
	head, it temporarily overrides current_message_id so the branch
	query walks from the correct leaf.

	each sdk message carries its orm id in metadata["message_id"]
	so downstream filters can identify messages without needing a
	separate lookup.

	returns (sdk_thread, current_message_id) so callers can derive
	the parent id for new messages without a separate query.
	"""
	thread_orm = await thread_service.get_thread(
		thread_id,
		session,
		principal=principal,
	)
	head_id = thread_orm.current_message_id

	# determine effective head. if caller provides an explicit parent_id,
	# temporarily point the ORM object there so get_current_branch follows
	# the correct branch.
	original_head = head_id
	if parent_id and original_head != parent_id:
		thread_orm.current_message_id = parent_id

	try:
		branch_orm = await thread_service.get_current_branch(
			thread_id,
			session,
			principal=principal,
			include_hidden=False,
		)

		# each sdk message carries its orm id in metadata so downstream
		# code (filters, event queries) can identify messages without a
		# separate metadata key on the thread.
		sdk_messages = []
		for m in branch_orm:
			sdk = m.to_sdk()
			enriched = {**(sdk.metadata or {}), "message_id": str(m.id)}
			sdk_messages.append(sdk.model_copy(update={"metadata": enriched}))

		sdk_thread = SDKThread(
			created_at=thread_orm.created_at,
			messages=sdk_messages,
			metadata=thread_orm.metadata_ or {},
		)
		return sdk_thread, head_id
	finally:
		# restore original head so ORM state is untouched
		if parent_id and original_head != parent_id:
			thread_orm.current_message_id = original_head


async def inject_system_instructions(
	agent_orm: AgentORM,
	thread: SDKThread,
	*,
	session: AsyncSession,
	principal: Principal | None = None,
	client_context: ClientContext | None = None,
) -> SDKThread:
	"""inject an agent's rendered system instructions at the start of a thread."""
	if not agent_orm.system_prompt:
		return thread

	user = principal.user if principal else None
	rendered = await render_agent_instructions(
		session,
		text=agent_orm.system_prompt,
		user=user,
		client_context=client_context,
	)
	if not rendered:
		return thread

	system_msg = SDKSystemMessage.from_text(rendered)
	return thread.model_copy(update={"messages": [system_msg, *thread.messages]})
