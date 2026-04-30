"""runs service - orchestrates agent run lifecycle.

every agent run executes the same way regardless of persistence or thread
binding: a background producer task drives the agent loop and publishes SSE
frames into the in-memory ``run_status_store``; HTTP callers subscribe to
those frames via ``subscribe_run_stream``. consequence: every run is
cancellable, observable, and resumable by any client with the right ACL,
and disconnecting the originator never kills the run.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from api.local_tasks import create_inline_background_task
from api.models.access_rule import AccessLevel
from api.schemas.runs import ClientContext, RunInput, ToolChoice
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadCreate
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_thread_access
from api.v1.service.chat import run_agent, run_bus
from api.v1.service.chat.run_status import run_status_store
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, is_typeid, new_typeid


logger = logging.getLogger(__name__)


class UnknownRunError(LookupError):
	"""raised when a caller subscribes to a run the store has no record of.

	distinct from "finished cleanly" so routers can map it to a 404 instead
	of streaming an empty done frame.
	"""


# how long to wait for the producer task to register the run before giving up.
# in practice this completes in microseconds (one event-loop tick); the only
# reason for any wait at all is to absorb scheduler jitter on busy workers.
_RUN_READY_TIMEOUT_S = 2.0


async def _run_producer(
	run_id: TypeID,
	ready_event: asyncio.Event,
	thread_id: TypeID | None,
	agent_id: TypeID,
	principal: Principal,
	input: RunInput | None,
	parent_id: TypeID | None,
	client_context: ClientContext | None,
	origin_session_id: str | None,
	tool_choice: ToolChoice | None,
	persist: bool,
) -> None:
	"""drive ``run_agent`` to completion as a background task.

	discards yielded SSE frames - they are already published to the
	run_status_store via ``publish()`` and consumed by HTTP subscribers.
	the producer is independent of any HTTP request lifecycle, so navigating
	away / disconnecting / reloading does NOT kill the run.

	on ``CancelledError`` (typically from ``cancel_run``), ``run_agent``'s
	own cancel handler publishes the terminal frames, calls ``fail_run``,
	and broadcasts ``run.error``; this function just lets the cancel
	propagate. on any other exception ``fail_run`` is called as a
	belt-and-suspenders safety net (it is idempotent).
	"""
	try:
		async for _ in run_agent(
			thread_id,
			agent_id,
			principal,
			input=input,
			parent_id=parent_id,
			client_context=client_context,
			origin_session_id=origin_session_id,
			persist=persist,
			tool_choice=tool_choice,
			run_id_override=run_id,
			ready_event=ready_event,
		):
			pass
	except asyncio.CancelledError:
		raise
	except Exception:
		logger.exception(
			"agent run producer crashed",
			extra={"run_id": run_id},
		)
	finally:
		# idempotent: no-op if the run completed naturally.
		await run_status_store.fail_run(run_id, reason="producer exited unexpectedly")


async def subscribe_run_stream(run_id: TypeID) -> AsyncGenerator[bytes]:
	"""subscribe to a run's SSE stream and replay catchup + live frames.

	this is the ONE SSE delivery path used by both the initiator (POST /v1/runs)
	and any later resume request (GET /v1/runs/{id}/stream). disconnecting from
	this stream only unsubscribes the caller - the producer keeps running.

	resolution order:

	1. local in-process subscription via ``run_status_store`` (zero hops, the
		common case when only one worker exists or when the request lands on
		the worker that owns the run).
	2. cross-worker subscription via ``run_bus.subscribe_remote_run`` when
		the run is unknown locally but redis reports a catchup log for it -
		meaning some other worker owns the producer.
	3. ``UnknownRunError`` if neither path knows about the run.
	"""
	result = await run_status_store.subscribe(run_id)
	if result is not None:
		catchup, live_queue = result
		try:
			for frame in catchup:
				yield frame
			while True:
				live_frame = await live_queue.get()
				if live_frame is None:
					yield sse_encode(event="done", data={})
					return
				yield live_frame
		finally:
			await run_status_store.unsubscribe(run_id, live_queue)
		return

	if await run_bus.remote_run_known(run_id):
		async for frame in run_bus.subscribe_remote_run(run_id):
			yield frame
		# remote path ends naturally; synthesize the done event so the wire
		# contract matches the local path.
		yield sse_encode(event="done", data={})
		return

	raise UnknownRunError(run_id)


async def _start_run(
	thread_id: TypeID | None,
	agent_id: TypeID,
	principal: Principal,
	input: RunInput | None,
	parent_id: TypeID | None,
	client_context: ClientContext | None,
	origin_session_id: str | None,
	tool_choice: ToolChoice | None,
	persist: bool = True,
) -> TypeID:
	"""spawn the producer task and wait for the run to be registered.

	the producer self-attaches its task to ``RunStatus`` from inside
	``run_agent`` (immediately after ``start_run``) so cancellation works
	from the very first microsecond the run is visible in the store.
	no post-spawn ``attach_task`` race window exists.
	"""
	run_id = new_typeid("run")
	ready_event = asyncio.Event()

	task = create_inline_background_task(
		_run_producer(
			run_id,
			ready_event,
			thread_id=thread_id,
			agent_id=agent_id,
			principal=principal,
			input=input,
			parent_id=parent_id,
			client_context=client_context,
			origin_session_id=origin_session_id,
			tool_choice=tool_choice,
			persist=persist,
		),
		name=f"agent_run:{run_id}",
	)

	try:
		await asyncio.wait_for(ready_event.wait(), timeout=_RUN_READY_TIMEOUT_S)
	except TimeoutError:
		task.cancel()
		try:
			await task
		except (asyncio.CancelledError, Exception):
			pass
		await run_status_store.fail_run(run_id, reason="producer failed to start")
		raise

	return run_id


async def start_thread_run(
	session: AsyncSession,
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

	the run executes as a background producer task that publishes frames
	to the run_status_store; this caller subscribes to those frames.
	clients can disconnect, reconnect, and resume freely without affecting
	the run. ``persist`` only gates DB writes - it does NOT change the
	background-task lifecycle, so non-persisted runs are still cancellable
	and observable via the store.

	the caller is responsible for wrapping the iterator in ``sse_response()``.
	"""
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)

	run_id = await _start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=principal,
		input=input,
		parent_id=parent_id,
		client_context=client_context,
		origin_session_id=origin_session_id,
		tool_choice=tool_choice,
		persist=persist,
	)
	return subscribe_run_stream(run_id)


async def start_ephemeral_run(
	agent_id: TypeID,
	principal: Principal,
	input: RunInput,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	tool_choice: ToolChoice | None = None,
) -> AsyncIterator[bytes]:
	"""start a thread-less, non-persisted inference run.

	uses the same producer-task path as persisted runs so the run is
	cancellable and observable via the store. without a thread_id no
	cross-user broadcast is performed; the only subscriber is normally
	the originating HTTP request, but in-process callers may still
	subscribe via the run_id.

	the caller is responsible for wrapping the iterator in ``sse_response()``.
	"""
	run_id = await _start_run(
		thread_id=None,
		agent_id=agent_id,
		principal=principal,
		input=input,
		parent_id=None,
		client_context=client_context,
		origin_session_id=origin_session_id,
		tool_choice=tool_choice,
		persist=False,
	)
	return subscribe_run_stream(run_id)


async def create_thread_and_run_stream(
	session: AsyncSession,
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

		run_id = await _start_run(
			thread_id=final_thread_id,
			agent_id=agent_id,
			principal=principal,
			input=input,
			parent_id=None,
			client_context=client_context,
			origin_session_id=origin_session_id,
			tool_choice=tool_choice,
			persist=True,
		)
		async for chunk in subscribe_run_stream(run_id):
			yield chunk

	return _stream()
