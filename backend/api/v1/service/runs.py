"""runs service — orchestrates agent run lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.schemas.runs import ClientContext
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadCreate
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_thread_access
from api.v1.service.chat import run_agent as chat_run_agent
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID


async def start_thread_run(
	session: AsyncSession,
	*,
	thread_id: TypeID,
	agent_id: TypeID,
	principal: Principal,
	input: str | None = None,
	parent_id: TypeID | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
) -> AsyncIterator[bytes]:
	"""validate access and return a streaming agent run on an existing thread.

	the caller is responsible for wrapping the iterator in ``sse_response()``.
	"""
	await require_thread_access(
		str(thread_id),
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)

	return chat_run_agent(
		thread_id,
		agent_id,
		principal,
		input=input,
		parent_id=parent_id,
		client_context=client_context,
		origin_session_id=origin_session_id,
	)


async def create_thread_and_run_stream(
	session: AsyncSession,
	*,
	principal: Principal,
	agent_id: TypeID,
	input: str,
	is_temporary: bool = False,
	tags: list[str] | None = None,
	project_ids: list[TypeID] | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
) -> AsyncIterator[bytes]:
	"""create a thread and return a streaming agent run.

	the first SSE event is ``thread_created`` with the full thread payload.
	subsequent events are normal run deltas.

	the caller is responsible for wrapping the iterator in ``sse_response()``.
	"""
	owner_id = TypeID(principal.user.id)

	thread = await thread_service.create_thread(
		ThreadCreate(
			owner_id=owner_id,
			is_temporary=is_temporary,
			tags=tags or [],
			project_ids=project_ids or [],
		),
		session,
		principal=principal,
		origin_session_id=origin_session_id,
	)
	thread_id = TypeID(thread.id)

	async def _stream() -> AsyncIterator[bytes]:
		thread_schema = ThreadSchema.model_validate(thread)
		yield sse_encode(event="thread_created", data=thread_schema)

		async for chunk in chat_run_agent(
			thread_id,
			agent_id,
			principal,
			input=input,
			client_context=client_context,
			origin_session_id=origin_session_id,
		):
			yield chunk

	return _stream()


async def start_ephemeral_run(
	*,
	agent_id: TypeID,
	principal: Principal,
	input: str,
	client_context: ClientContext | None = None,
) -> AsyncIterator[bytes]:
	"""run a one-turn ephemeral inference (no persisted thread).

	NOT IMPLEMENTED — placeholder for future work.
	"""
	raise HTTPException(
		status_code=status.HTTP_501_NOT_IMPLEMENTED,
		detail="ephemeral runs are not yet implemented",
	)
