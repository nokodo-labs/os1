"""runs service - orchestrates agent run lifecycle."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.schemas.runs import ClientContext, RunInput, ToolChoice
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadCreate
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_thread_access
from api.v1.service.chat import run_agent as chat_run_agent
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, is_typeid


logger = logging.getLogger(__name__)


async def start_thread_run(
	session: AsyncSession,
	*,
	thread_id: TypeID,
	agent_id: TypeID,
	principal: Principal,
	input: RunInput | None = None,
	parent_id: TypeID | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	persist: bool = True,
	tool_choice: ToolChoice | None = None,
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
		persist=persist,
		tool_choice=tool_choice,
	)


async def create_thread_and_run_stream(
	session: AsyncSession,
	*,
	principal: Principal,
	agent_id: TypeID,
	input: RunInput,
	thread_id: TypeID | None = None,
	is_temporary: bool = False,
	tags: list[str] | None = None,
	project_ids: list[TypeID] | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	tool_choice: ToolChoice | None = None,
) -> AsyncIterator[bytes]:
	"""create a thread and return a streaming agent run.

	if ``thread_id`` is provided and valid, the backend will use it as the
	thread's primary key. on conflict (extremely unlikely), a new ID is
	generated instead - the ``thread_created`` SSE event always carries the
	canonical ID.

	the first SSE event is ``thread_created`` with the full thread payload.
	subsequent events are normal run deltas.

	the caller is responsible for wrapping the iterator in ``sse_response()``.
	"""
	owner_id = TypeID(principal.user.id)

	# validate client-provided ID shape
	use_client_id = thread_id is not None and is_typeid(thread_id, prefix="thread")

	thread_create = ThreadCreate(
		owner_id=owner_id,
		is_temporary=is_temporary,
		tags=tags or [],
		project_ids=project_ids or [],
	)

	if use_client_id:
		from sqlalchemy.exc import IntegrityError

		try:
			thread = await thread_service.create_thread(
				thread_create,
				session,
				principal=principal,
				origin_session_id=origin_session_id,
				override_id=thread_id,
			)
		except IntegrityError:
			await session.rollback()
			logger.info("client thread id %s conflicted, generating new id", thread_id)
			thread = await thread_service.create_thread(
				thread_create,
				session,
				principal=principal,
				origin_session_id=origin_session_id,
			)
	else:
		thread = await thread_service.create_thread(
			thread_create,
			session,
			principal=principal,
			origin_session_id=origin_session_id,
		)

	final_thread_id = TypeID(thread.id)

	async def _stream() -> AsyncIterator[bytes]:
		thread_schema = ThreadSchema.model_validate(thread)
		yield sse_encode(event="thread_created", data=thread_schema)

		async for chunk in chat_run_agent(
			final_thread_id,
			agent_id,
			principal,
			input=input,
			client_context=client_context,
			origin_session_id=origin_session_id,
			tool_choice=tool_choice,
		):
			yield chunk

	return _stream()
