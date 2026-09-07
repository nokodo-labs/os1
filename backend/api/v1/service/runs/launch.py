"""runs service - orchestrates agent run lifecycle.

every agent run executes the same way regardless of persistence or thread
binding: a background producer task drives the agent loop, which publishes SSE
frames into the run stream store; HTTP callers subscribe to
those frames via ``subscribe_run_stream``. consequence: every run is
cancellable, observable, and resumable by any client with the right ACL,
and disconnecting the originator never kills the run.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.advisory_locks import acquire_resource_write_lock
from api.database.post_commit import discard_uncommitted_post_commit_actions
from api.local_tasks import create_background_task
from api.models.access_rule import AccessLevel
from api.models.thread import Thread
from api.permissions import MentionableSubjectType
from api.schemas.common import MISSING
from api.schemas.message import MessageCreate, MessageSplice, RunBlockRef
from api.schemas.runs import (
	ClientContext,
	ToolChoice,
)
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadCreate
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	public_payload,
	require_thread_access,
)
from api.v1.service.chat.messages import (
	orm_message_to_sdk_message,
	validate_message_input,
)
from api.v1.service.runs.bus import (
	RunBusUnavailableError,
	read_run_route,
	subscribe_remote_run,
)
from api.v1.service.runs.contracts import (
	BUS_UNAVAILABLE_REASON,
	PersistedRunInput,
	RunFailureReason,
	run_failure_payload,
)
from api.v1.service.runs.execution import run_agent
from api.v1.service.runs.failures import terminate_run
from api.v1.service.runs.status import StartNewRun, agent_slots, run_streams
from api.v1.service.runs.steering_bus import SteeringUnavailableError
from api.v1.service.threads import (
	MessageDraft,
	branch_root_id,
	create_message,
	create_thread,
	message_is_visible,
	message_mentions_agent,
	require_run_context_message,
)
from api.v1.service.threads.common import message_created_frame_data
from api.v1.service.threads.messages.writes import WrittenMessage
from api.v1.service.threads.splices import (
	PreparedPlacement,
	prepare_message_placement,
)
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, is_typeid, new_typeid


logger = logging.getLogger(__name__)


class RunStartupError(HTTPException):
	"""startup failure carrying whether the run reached the registry."""

	def __init__(
		self,
		run_id: TypeID,
		run_registered: bool = True,
		detail: str = "agent run failed to start",
	) -> None:
		"""carry whether the run reached the registry before it failed.

		an invocation retries against a run that never registered, and reports
		one that did as undelivered rather than never started.
		"""
		super().__init__(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail=detail,
		)
		self.run_id = run_id
		self.run_registered = run_registered


_RUN_READY_TIMEOUT_S = 7.0
"""how long a launcher waits for its producer to announce readiness.

longer than the 5-second thread write-lock budget a persisted input write can
spend, so a busy thread times out on the lock rather than here.
"""

_STEERING_UNAVAILABLE_DETAIL = (
	"agent runs are temporarily unavailable; please try again shortly"
)
"""told to a client when a run cannot start because it would be unsteerable."""


@dataclass(slots=True)
class _StartupOutcome:
	"""how a producer's startup ended, for the launcher racing it."""

	error: BaseException | None = None
	"""what killed the producer, when it died before announcing readiness."""


async def _stream_delivery_checkpoint() -> None:
	"""allow disconnect cancellation to interrupt large catchup bursts."""
	await asyncio.sleep(0)


async def _run_producer(
	run_id: TypeID,
	ready_event: asyncio.Event,
	registered_event: asyncio.Event,
	outcome: _StartupOutcome,
	thread_id: TypeID | None,
	agent_id: TypeID,
	principal: Principal,
	input: MessageCreate | None,
	splice: MessageSplice | None,
	client_context: ClientContext | None,
	origin_session_id: str | None,
	tool_choice: ToolChoice | None,
	extra_plugins: list[str],
	persist: bool,
	invoking_message_id: TypeID | None = None,
	persisted_input: PersistedRunInput | None = None,
) -> None:
	"""drive ``run_agent`` to completion as a background task.

	SSE frames are published directly to the run stream store and consumed by
	HTTP subscribers.
	the producer is independent of any HTTP request lifecycle, so navigating
	away / disconnecting / reloading does NOT kill the run.

	on ``CancelledError`` (typically from ``cancel_run``), ``run_agent``'s
	own cancel handler publishes the terminal frames, calls ``fail_run``,
	and broadcasts ``run.error``; this function just lets the cancel
	propagate. on any other exception ``fail_run`` is called as a
	belt-and-suspenders safety net (it is idempotent).
	"""
	failure_reason = "generation failed"
	try:
		await run_agent(
			thread_id,
			agent_id,
			principal,
			input=input,
			splice=splice,
			client_context=client_context,
			origin_session_id=origin_session_id,
			persist=persist,
			tool_choice=tool_choice,
			extra_plugins=extra_plugins,
			run_id_override=run_id,
			ready_event=ready_event,
			registered_event=registered_event,
			invoking_message_id=invoking_message_id,
			persisted_input=persisted_input,
		)
	except asyncio.CancelledError:
		failure_reason = "cancelled"
		raise
	except RunBusUnavailableError as exc:
		# the durable record says the same thing the live frame does: a
		# backend was unreachable and this is worth retrying, not a bug.
		outcome.error = exc
		failure_reason = BUS_UNAVAILABLE_REASON
		logger.warning(
			"agent run producer lost the run bus",
			extra={"run_id": run_id, "operation": exc.operation},
		)
	except SteeringUnavailableError as exc:
		outcome.error = exc
		failure_reason = BUS_UNAVAILABLE_REASON
		logger.warning(
			"agent run producer could not attach its steering subscriber",
			extra={"run_id": run_id},
		)
	except Exception as exc:
		outcome.error = exc
		logger.exception(
			"agent run producer crashed",
			extra={"run_id": run_id},
		)
	finally:
		# idempotent: no-op if the run completed naturally.
		await terminate_run(run_id, reason=failure_reason)


async def subscribe_run_stream(
	run_id: TypeID,
	subscriber_id: TypeID,
) -> AsyncGenerator[bytes]:
	"""subscribe to a run's SSE stream and replay catchup + live frames.

	this is the one SSE delivery path used by both the initiator (POST /v1/runs)
	and any later resume request (GET /v1/runs/{id}/stream). disconnecting from
	this stream only unsubscribes the caller - the producer keeps running.

	``subscriber_id`` is the user the caller was authorized as, recorded so a
	revocation landing mid-run can end this stream without touching the run.

	resolution order:

	1. local in-process subscription via ``run_streams`` (zero hops, the
		common case when only one worker exists or when the request lands on
		the worker that owns the run).
	2. cross-worker subscription via ``run_bus.subscribe_remote_run`` when
		the run is unknown locally but redis reports a catchup log for it -
		meaning some other worker owns the producer.
	3. a terminal ``done`` when neither path knows about the run: every caller
		wraps this in an SSE response whose status line is committed before
		the first frame is pulled, so a run that ended between the caller's
		lookup and this subscribe must close the way a completion does rather
		than raise into an already-committed body.
	"""
	result = await run_streams.subscribe(run_id, subscriber_id)
	if result is not None:
		catchup, live_queue = result
		try:
			for frame in catchup:
				yield frame
				await _stream_delivery_checkpoint()
			while True:
				live_frame = await live_queue.get()
				if live_frame is None:
					yield sse_encode(event="done", data={})
					return
				yield live_frame
				await _stream_delivery_checkpoint()
		finally:
			await run_streams.unsubscribe(run_id, live_queue)

	try:
		route = await read_run_route(run_id)
	except RunBusUnavailableError:
		# the status line is already committed, so this closes the way a
		# failure does rather than raising a 503 into an open body. "we cannot
		# tell" is reported as an error, never as a quiet completion, and as
		# unavailable rather than internal: retrying is the right move, and
		# calling it a bug would ask the client to report one instead.
		logger.warning("run bus unreachable while attaching stream for %s", run_id)
		yield sse_encode(
			event="error",
			data=run_failure_payload(
				thread_id=None,
				agent_id=None,
				reason=RunFailureReason.UNAVAILABLE,
				run_id=run_id,
			),
		)
		yield sse_encode(event="done", data={})
		return

	if route is not None:
		async for frame in subscribe_remote_run(run_id, subscriber_id):
			yield frame
			await _stream_delivery_checkpoint()
		# remote path ends naturally; synthesize the done event so the wire
		# contract matches the local path.
		yield sse_encode(event="done", data={})
		return

	logger.info("run %s ended before its stream attached", run_id)
	yield sse_encode(event="done", data={})


async def _start_run(
	thread_id: TypeID | None,
	agent_id: TypeID,
	principal: Principal,
	input: MessageCreate | None,
	splice: MessageSplice | None,
	client_context: ClientContext | None,
	origin_session_id: str | None,
	tool_choice: ToolChoice | None,
	extra_plugins: list[str],
	persist: bool = True,
	invoking_message_id: TypeID | None = None,
	run_id: TypeID | None = None,
	persisted_input: PersistedRunInput | None = None,
) -> TypeID:
	"""spawn the producer task and wait for the run to be registered.

	the producer self-attaches its task to ``RunStatus`` from inside
	``run_agent`` (immediately after ``start_run``) so cancellation works
	from the very first microsecond the run is visible in the store.
	no post-spawn ``attach_task`` race window exists.
	"""
	run_id = run_id or new_typeid("run")
	ready_event = asyncio.Event()
	registered_event = asyncio.Event()
	outcome = _StartupOutcome()

	task = create_background_task(
		_run_producer(
			run_id,
			ready_event,
			registered_event,
			outcome,
			thread_id=thread_id,
			agent_id=agent_id,
			principal=principal,
			input=input,
			splice=splice,
			client_context=client_context,
			origin_session_id=origin_session_id,
			tool_choice=tool_choice,
			extra_plugins=extra_plugins,
			persist=persist,
			invoking_message_id=invoking_message_id,
			persisted_input=persisted_input,
		),
		name=f"agent_run:{run_id}",
	)

	# the producer is raced against the readiness signal rather than waited out:
	# a producer that died before announcing readiness has already failed, and
	# holding the request for the full timeout only delays the 503.
	ready_wait = asyncio.ensure_future(ready_event.wait())
	try:
		await asyncio.wait(
			{ready_wait, task},
			timeout=_RUN_READY_TIMEOUT_S,
			return_when=asyncio.FIRST_COMPLETED,
		)
	finally:
		ready_wait.cancel()

	if ready_event.is_set():
		return run_id

	task.cancel()
	current = asyncio.current_task()
	try:
		await task
	except asyncio.CancelledError:
		# cancelling `task` above lands here; a cancellation aimed at THIS
		# caller has to keep propagating rather than be absorbed as the
		# producer's.
		if current is not None and current.cancelling():
			raise
	except Exception:
		logger.exception(
			"agent run producer failed to start",
			extra={"run_id": run_id},
		)
	await terminate_run(run_id, reason="producer failed to start")
	raise RunStartupError(
		run_id,
		run_registered=registered_event.is_set(),
		detail=(
			_STEERING_UNAVAILABLE_DETAIL
			if isinstance(outcome.error, SteeringUnavailableError)
			else "agent run failed to start"
		),
	) from None


async def launch_invoked_run(
	session: AsyncSession,
	thread_id: TypeID,
	agent_id: TypeID,
	principal: Principal,
	invoking_message_id: TypeID,
	origin_session_id: str | None = None,
) -> TypeID:
	"""start a run whose invocation the server resolved under the write lock."""
	await _preflight_thread_run(
		session,
		thread_id=thread_id,
		principal=principal,
		input=None,
		splice=None,
		persist=True,
		invoking_message_id=invoking_message_id,
	)
	return await _execute_run_on_thread(
		session,
		thread_id=thread_id,
		agent_id=agent_id,
		principal=principal,
		input=None,
		invoking_message_id=invoking_message_id,
		splice=None,
		origin_session_id=origin_session_id,
	)


async def launch_thread_run(
	session: AsyncSession,
	thread_id: TypeID,
	agent_id: TypeID,
	principal: Principal,
	input: MessageCreate | None = None,
	splice: MessageSplice | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	persist: bool = True,
	tool_choice: ToolChoice | None = None,
	extra_plugins: list[str] | None = None,
	invoking_message_id: TypeID | None = None,
) -> TypeID:
	"""validate access, start a run on an existing thread, and name it.

	the run itself is a background producer, so a caller that does not need
	the SSE frames (the server invoking an agent on a user's behalf) takes
	the id and lets subscribers attach through ``run.started``.

	"""
	validate_message_input(input)
	if input is not None and any(
		mention.type == MentionableSubjectType.AGENT and mention.id != agent_id
		for mention in input.mentions
	):
		raise HTTPException(
			status_code=status.HTTP_501_NOT_IMPLEMENTED,
			detail="invoking another agent from run input is not implemented",
		)
	thread = await _preflight_thread_run(
		session,
		thread_id=thread_id,
		principal=principal,
		input=input,
		splice=splice,
		persist=persist,
		invoking_message_id=invoking_message_id,
	)
	if invoking_message_id is not None:
		if input is not None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="an invoked run answers the mention, so it takes no input",
			)
		if splice is not None and splice.replaces is not None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="an invoked run cannot replace existing output",
			)
		if not await message_mentions_agent(
			session, thread_id, invoking_message_id, agent_id
		):
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="message does not mention this agent",
			)
		if not await message_is_visible(
			session,
			thread_id,
			invoking_message_id,
		):
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="message not found in this thread",
			)
		splice = None

	prospective_message_id = new_typeid("msg") if persist and input else None
	placement: PreparedPlacement | None = None
	if prospective_message_id is not None:
		# the slot names the conversation this run answers, and the message
		# decides which conversation that is - so the placement is derived once
		# here, under the lock the write also holds, and handed to the write.
		await acquire_resource_write_lock(session, "thread", thread_id)
		placement = await prepare_message_placement(
			session,
			thread,
			splice if splice is not None else MISSING,
			prospective_message_id,
			principal=principal,
		)
		container_root_id = placement.container_root_id
	else:
		container_message_id = invoking_message_id
		if container_message_id is None and splice is not None:
			if splice.replaces is not None:
				container_message_id = (
					splice.replaces.run_head_message_id
					if isinstance(splice.replaces, RunBlockRef)
					else splice.replaces.head_id
				)
			else:
				container_message_id = splice.parent_id
		container_root_id = (
			await branch_root_id(session, thread_id, container_message_id)
			if container_message_id is not None
			else None
		)
	claim = await agent_slots.claim(
		thread_id,
		agent_id,
		container_root_id,
	)
	if not isinstance(claim, StartNewRun):
		if prospective_message_id is not None:
			await session.rollback()
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="this agent already has a run in this conversation",
		)
	run_id: TypeID | None = None
	try:
		run_id = await _execute_run_on_thread(
			session,
			thread_id=thread_id,
			agent_id=agent_id,
			principal=principal,
			input=input,
			splice=splice,
			client_context=client_context,
			origin_session_id=origin_session_id,
			persist=persist,
			tool_choice=tool_choice,
			extra_plugins=extra_plugins,
			invoking_message_id=invoking_message_id,
			run_id=new_typeid("run"),
			persisted_input_message_id=prospective_message_id,
			placement=placement,
		)
		return run_id
	finally:
		await agent_slots.release(
			thread_id,
			agent_id,
			container_root_id,
			claim.slot,
			run_id,
		)


async def _preflight_thread_run(
	session: AsyncSession,
	thread_id: TypeID,
	principal: Principal,
	input: MessageCreate | None,
	splice: MessageSplice | None,
	persist: bool,
	invoking_message_id: TypeID | None,
) -> Thread:
	"""authorize and validate a thread run without mutating run state."""
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	thread = await session.get(Thread, thread_id)
	if thread is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="thread not found",
		)
	if splice is not None and splice.parent_id is not None:
		await require_run_context_message(session, thread_id, splice.parent_id)

	if splice is not None and splice.replaces is not None:
		if input is not None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="run-block replacement cannot include a new input message",
			)
		if not persist:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="run-block replacement requires persistence",
			)
	if (
		input is None
		and invoking_message_id is None
		and thread.current_message_id is None
		and (splice is None or splice.replaces is None)
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="an empty thread run requires input",
		)
	return thread


async def _execute_run_on_thread(
	session: AsyncSession,
	thread_id: TypeID,
	agent_id: TypeID,
	principal: Principal,
	input: MessageCreate | None,
	splice: MessageSplice | None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	persist: bool = True,
	tool_choice: ToolChoice | None = None,
	extra_plugins: list[str] | None = None,
	invoking_message_id: TypeID | None = None,
	run_id: TypeID | None = None,
	persisted_input_message_id: TypeID | None = None,
	placement: PreparedPlacement | None = None,
) -> TypeID:
	"""persist input and start an already-preflighted thread run."""
	run_id = run_id or new_typeid("run")
	persisted_input: PersistedRunInput | None = None
	if persist and input is not None:
		draft = MessageDraft.from_request(input)
		draft.splice = splice if splice is not None else MISSING
		draft.metadata["run_id"] = str(run_id)
		written = await create_message(
			thread_id,
			draft,
			session,
			principal=principal,
			placement=placement,
			message_id=persisted_input_message_id,
			origin_session_id=origin_session_id,
			originated_resources=input.originated_resources,
		)
		persisted_input = _capture_run_input(written)
	return await _start_run(
		thread_id=thread_id,
		agent_id=agent_id,
		principal=principal,
		input=None if persisted_input is not None else input,
		splice=None if persisted_input is not None else splice,
		client_context=client_context,
		origin_session_id=origin_session_id,
		tool_choice=tool_choice,
		extra_plugins=extra_plugins or [],
		persist=persist,
		invoking_message_id=invoking_message_id,
		run_id=run_id,
		persisted_input=persisted_input,
	)


def _capture_run_input(written: WrittenMessage) -> PersistedRunInput:
	"""read everything the run needs off the row the write just committed."""
	sdk_message = orm_message_to_sdk_message(written.message)
	if not isinstance(sdk_message, SDKUserMessage):
		raise RuntimeError("persisted run input is not a user message")
	return PersistedRunInput(
		message_id=written.message.id,
		splice=written.splice,
		sdk_message=sdk_message,
		created_frame=message_created_frame_data(written.message, written.splice),
		container_root_id=written.container_root_id,
	)


async def start_ephemeral_run(
	agent_id: TypeID,
	principal: Principal,
	input: MessageCreate,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	tool_choice: ToolChoice | None = None,
	extra_plugins: list[str] | None = None,
) -> AsyncIterator[bytes]:
	"""start a thread-less, non-persisted inference run.

	uses the same producer-task path as persisted runs so the run is
	cancellable and observable via the store. without a thread_id no
	cross-user broadcast is performed; the only subscriber is normally
	the originating HTTP request, but in-process callers may still
	subscribe via the run_id.

	the caller is responsible for wrapping the iterator in ``sse_response()``.
	"""
	validate_message_input(input)
	run_id = await _start_run(
		thread_id=None,
		agent_id=agent_id,
		principal=principal,
		input=input,
		splice=None,
		client_context=client_context,
		origin_session_id=origin_session_id,
		tool_choice=tool_choice,
		extra_plugins=extra_plugins or [],
		persist=False,
	)
	return subscribe_run_stream(run_id, principal.user.id)


async def create_thread_and_run_stream(
	session: AsyncSession,
	principal: Principal,
	agent_id: TypeID,
	input: MessageCreate,
	thread_id: TypeID | None = None,
	is_temporary: bool = False,
	tags: list[str] | None = None,
	project_ids: list[TypeID] | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	tool_choice: ToolChoice | None = None,
	extra_plugins: list[str] | None = None,
) -> AsyncIterator[bytes]:
	"""create a thread and return a streaming agent run.

	if ``thread_id`` is provided and valid, the backend will use it as the
	thread's primary key. on conflict (extremely unlikely), a new ID is
	generated instead - the ``thread_created`` SSE event always carries the
	canonical ID.

	the first SSE event is ``thread_created`` with the full thread payload.
	subsequent events are normal run deltas.

	the run must start before the response does, so a refusal raises here and
	the client reads it as an HTTP error rather than as a frame inside a 200.

	the caller is responsible for wrapping the iterator in ``sse_response()``.
	"""
	validate_message_input(input)
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
		try:
			thread = await create_thread(
				thread_create,
				session,
				principal=principal,
				origin_session_id=origin_session_id,
				override_id=thread_id,
			)
		except IntegrityError:
			# the conflict surfaces on the creation's flush, and the rolled-back
			# attempt already queued its fanout; without this the retry's commit
			# would promote and run both sets.
			discard_uncommitted_post_commit_actions(session)
			await session.rollback()
			logger.info("client thread id %s conflicted, generating new id", thread_id)
			thread = await create_thread(
				thread_create,
				session,
				principal=principal,
				origin_session_id=origin_session_id,
			)
	else:
		thread = await create_thread(
			thread_create,
			session,
			principal=principal,
			origin_session_id=origin_session_id,
		)

	final_thread_id = thread.id

	# the run is launched before the response, on the SAME uncommitted session:
	# a refusal is an HTTP error the client already handles, and rolls the
	# thread back with it rather than leaving an empty one nobody asked for.
	# the input-message write inside commits the thread and the message
	# together. a stream that opens is a stream that has a run.
	try:
		run_id = await launch_thread_run(
			session,
			final_thread_id,
			agent_id,
			principal,
			input=input,
			client_context=client_context,
			origin_session_id=origin_session_id,
			tool_choice=tool_choice,
			extra_plugins=extra_plugins or [],
		)
	except BaseException:
		discard_uncommitted_post_commit_actions(session)
		await session.rollback()
		raise
	thread_schema = public_payload(ThreadSchema.model_validate(thread))

	async def _stream() -> AsyncIterator[bytes]:
		"""announce the new thread, then stream the run already started in it."""
		yield sse_encode(event="thread_created", data=thread_schema)
		# the status line and thread_created are already on the wire, so a
		# failure here closes the way a run failure does rather than truncating
		# the body with neither an error nor a done.
		try:
			async for chunk in subscribe_run_stream(run_id, principal.user.id):
				yield chunk
		except RunBusUnavailableError as exc:
			# a backend we could not reach is worth retrying, and saying
			# "internal_error" would ask the client to report a bug instead.
			logger.warning(
				"create-and-run stream lost the run bus",
				extra={"run_id": str(run_id), "operation": exc.operation},
			)
			yield sse_encode(
				event="error",
				data=run_failure_payload(
					thread_id=final_thread_id,
					agent_id=agent_id,
					reason=RunFailureReason.UNAVAILABLE,
					run_id=run_id,
				),
			)
			yield sse_encode(event="done", data={})
		except Exception:
			logger.exception(
				"create-and-run stream failed while delivering frames",
				extra={"run_id": str(run_id), "thread_id": str(final_thread_id)},
			)
			yield sse_encode(
				event="error",
				data=run_failure_payload(
					thread_id=final_thread_id,
					agent_id=agent_id,
					reason=RunFailureReason.INTERNAL_ERROR,
					run_id=run_id,
				),
			)
			yield sse_encode(event="done", data={})

	return _stream()
