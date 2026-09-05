"""ordered durable output writes for one agent run.

the actor owns cancellation-safe write reconciliation and serializes output,
steering parent advances, barriers, and close as one ordered state machine.
"""

import asyncio
import logging
from dataclasses import dataclass

from api.database import async_session_local
from api.local_tasks import create_background_task
from api.models.event import Event
from api.models.message import Message
from api.schemas.message import Citation, MessageSplice
from api.v1.service.authentication import Principal
from api.v1.service.chat.messages import prepare_generated_message
from api.v1.service.runs.status import run_conversations, run_streams
from api.v1.service.threads import branch_root_id
from api.v1.service.threads.common import message_created_frame_data
from api.v1.service.threads.messages.writes import (
	CommittedMessageWriteError,
	create_message_at_run_tail_with_commit_outcome,
	create_message_with_commit_outcome,
)
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import FinishReason
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)


class RunOutputWriterClosedError(RuntimeError):
	"""the run output writer no longer accepts commands."""


class MessageReservationAbandonedError(RuntimeError):
	"""a reserved message was never submitted before the writer closed."""


def observe_future_completion[T](future: asyncio.Future[T]) -> None:
	"""consume a background future exception after its owner stops awaiting it."""
	if future.cancelled():
		return
	try:
		future.exception()
	except BaseException:
		pass


@dataclass(frozen=True, slots=True)
class RunOutputContext:
	"""immutable inputs shared by every output write in one run."""

	run_id: TypeID
	"""the run these writes belong to."""
	thread_id: TypeID
	"""the conversation being written into."""
	agent_id: TypeID
	"""the agent whose answers this writer persists."""
	principal: Principal
	"""who the writes are performed as."""
	origin_session_id: str | None
	"""client session that started the run, excluded from its own fanout."""
	model_id: str | None
	"""model stamped onto each generated row, for later attribution."""
	initial_parent_id: TypeID | None
	"""message the run's first output chains onto."""
	first_splice: MessageSplice | None
	"""explicit placement for the first output, including a replacement."""


@dataclass(frozen=True, slots=True)
class MessageReservation:
	"""an output message id reserved before its deltas are published."""

	message_id: TypeID
	"""the id deltas stream under, before any row exists to hold it."""


@dataclass(frozen=True, slots=True)
class MessageCommitReceipt:
	"""durable placement of one run output message."""

	message_id: TypeID
	"""the committed row's id, which matches its reservation."""
	parent_id: TypeID | None
	"""what the row was actually chained onto."""
	container_root_id: TypeID | None
	"""the conversation it landed in; None for the canon conversation."""


@dataclass(frozen=True, slots=True)
class ParentAdvanceReceipt:
	"""confirmation that a parent change reached the actor."""

	parent_id: TypeID
	"""the parent subsequent output now chains onto."""


@dataclass(frozen=True, slots=True)
class BarrierReceipt:
	"""writer state after every earlier command completed."""

	replacement_committed: bool
	"""whether the run's first output has landed and replaced what it names."""


@dataclass(frozen=True, slots=True)
class WriteOutput:
	"""immutable snapshot of one completed generated message."""

	reservation: MessageReservation
	"""the id this message was published under before it was written."""
	message: SDKMessage
	"""what the agent produced, frozen at submit time."""
	reply_to_message_id: TypeID | None
	"""the invocation this output answers, when it opens a reply block."""
	read_through_message_id: TypeID | None
	"""the run's snapshot at submit time, which places this at its own tail."""
	citations: tuple[Citation, ...]
	"""sources resolved for this message, in citation order."""


@dataclass(frozen=True, slots=True)
class AdvanceParent:
	"""move the next output after an injected steering message."""

	parent_id: TypeID
	"""the message subsequent output chains onto."""
	completion: asyncio.Future[ParentAdvanceReceipt]
	"""resolves once the actor has applied the move."""


@dataclass(frozen=True, slots=True)
class Barrier:
	"""ordered writer observation command."""

	completion: asyncio.Future[BarrierReceipt]
	"""resolves with the writer's state once earlier commands finish."""


@dataclass(frozen=True, slots=True)
class Finish:
	"""drain earlier commands and stop the actor."""

	completion: asyncio.Future[None]
	"""resolves once the queue is drained and the actor has stopped."""


type RunOutputCommand = WriteOutput | AdvanceParent | Barrier | Finish
"""everything the actor's queue can carry, including its own shutdown."""
type PublicRunOutputCommand = WriteOutput | AdvanceParent | Barrier
"""what a caller may enqueue: ``Finish`` is the writer's to issue."""


@dataclass(frozen=True, slots=True)
class FirstOutputPlacement:
	"""splice applied to the first output message."""

	splice: MessageSplice
	"""where the run's first answer lands, including any replacement."""


@dataclass(frozen=True, slots=True)
class FollowingOutputPlacement:
	"""ordinary run-tail placement after the first output."""


type OutputPlacement = FirstOutputPlacement | FollowingOutputPlacement
"""how one output is placed: the run's first answer, or after its own tail."""


@dataclass(frozen=True, slots=True)
class _CommitEntry:
	"""one reserved output id and the signals its waiters await."""

	future: asyncio.Future[MessageCommitReceipt]
	"""resolves with the durable placement once the row commits."""
	processed: asyncio.Future[None]
	"""resolves once the run's own coordination for this row is done."""
	submitted: bool = False
	"""whether a queued write already owns this reservation."""


class MessageCommitTracker:
	"""correlate reserved output ids with durable message commits."""

	def __init__(self) -> None:
		"""start with nothing reserved and no failure to report."""
		self._entries: dict[TypeID, _CommitEntry] = {}
		self._tool_call_messages: dict[str, TypeID] = {}
		self._failure: BaseException | None = None

	def reserve(self) -> MessageReservation:
		"""reserve a message id and its commit signal."""
		if self._failure is not None:
			raise self._failure
		message_id = TypeID(new_typeid("msg"))
		future = asyncio.get_running_loop().create_future()
		future.add_done_callback(observe_future_completion)
		processed = asyncio.get_running_loop().create_future()
		processed.add_done_callback(observe_future_completion)
		self._entries[message_id] = _CommitEntry(
			future=future,
			processed=processed,
		)
		return MessageReservation(message_id=message_id)

	def submitted(self, reservation: MessageReservation) -> bool:
		"""whether a queued write owns the reservation."""
		entry = self._entries.get(reservation.message_id)
		return entry.submitted if entry is not None else False

	def mark_submitted(
		self,
		reservation: MessageReservation,
		tool_call_ids: tuple[str, ...] = (),
	) -> None:
		"""mark a reservation as owned by a queued write command."""
		self.validate_submission(reservation)
		entry = self._entries[reservation.message_id]
		self._entries[reservation.message_id] = _CommitEntry(
			future=entry.future,
			processed=entry.processed,
			submitted=True,
		)
		for tool_call_id in tool_call_ids:
			existing = self._tool_call_messages.get(tool_call_id)
			if existing is not None and existing != reservation.message_id:
				raise ValueError("tool call id belongs to another assistant message")
			self._tool_call_messages[tool_call_id] = reservation.message_id

	def validate_submission(self, reservation: MessageReservation) -> None:
		"""require an unresolved reservation that has not been submitted."""
		entry = self._entries.get(reservation.message_id)
		if entry is None:
			raise ValueError("unknown message reservation")
		if entry.submitted:
			raise ValueError("message reservation was already submitted")
		if entry.future.done():
			raise ValueError("message reservation is already settled")

	async def correlate_event(self, event: Event) -> None:
		"""resolve explicit message or tool-call correlation after commit.

		the anchor must name a committed row: the event table's ``message_id``
		is an FK, so persisting one that references a row still in flight would
		fail the insert. hence the wait - bounded because a run that never
		commits must not wedge its own event stream.
		"""
		message_id = event.message_id
		if message_id is None:
			tool_call_id = event.data.get("tool_call_id")
			if isinstance(tool_call_id, str):
				message_id = self._tool_call_messages.get(tool_call_id)
		if message_id is None:
			logger.warning(
				"persisting an unanchored run event",
				extra={"event_type": event.type},
			)
			return
		entry = self._entries.get(message_id)
		if entry is None:
			return
		try:
			async with asyncio.timeout(10):
				receipt = await asyncio.shield(entry.future)
		except asyncio.CancelledError:
			raise
		except TimeoutError:
			# unreachable while the stream loop awaits each commit before the
			# next delta; it stops being true the moment a caller emits
			# without that guarantee.
			logger.error(
				"timed out resolving a run event anchor",
				extra={"event_type": event.type, "message_id": str(message_id)},
			)
			event.message_id = None
		except Exception:
			# the anchor row never landed, so the FK cannot reference it.
			logger.warning(
				"dropping a run event anchor whose message failed to commit",
				extra={"event_type": event.type, "message_id": str(message_id)},
				exc_info=True,
			)
			event.message_id = None
		else:
			event.message_id = receipt.message_id

	async def require_committed(
		self, message_id: TypeID | None
	) -> MessageCommitReceipt | None:
		"""wait for a tracked parent commit and propagate its failure."""
		if message_id is None:
			return None
		entry = self._entries.get(message_id)
		if entry is None:
			return None
		return await asyncio.shield(entry.future)

	async def require_processed(self, message_id: TypeID | None) -> None:
		"""wait until post-commit run coordination has completed."""
		if message_id is None:
			return
		entry = self._entries.get(message_id)
		if entry is None:
			return
		await asyncio.shield(entry.processed)

	def committed(self, reservation: MessageReservation | None) -> bool:
		"""whether a reservation already has a durable commit outcome."""
		if reservation is None:
			return False
		entry = self._entries.get(reservation.message_id)
		if entry is None or not entry.future.done() or entry.future.cancelled():
			return False
		try:
			entry.future.result()
		except BaseException:
			return False
		return True

	def complete(
		self,
		reservation: MessageReservation,
		receipt: MessageCommitReceipt,
	) -> None:
		"""resolve one reservation after its row committed."""
		entry = self._entries.get(reservation.message_id)
		if entry is None or entry.future.done():
			return
		entry.future.set_result(receipt)

	def processed(self, reservation: MessageReservation) -> None:
		"""resolve one reservation after its message-created frame is ordered."""
		entry = self._entries.get(reservation.message_id)
		if entry is not None and not entry.processed.done():
			entry.processed.set_result(None)

	def fail(self, reservation: MessageReservation, error: BaseException) -> None:
		"""reject one reservation with the original write failure."""
		entry = self._entries.get(reservation.message_id)
		if entry is None:
			return
		if not entry.future.done():
			entry.future.set_exception(error)
		if not entry.processed.done():
			entry.processed.set_exception(error)

	def abandon(self, reservation: MessageReservation) -> None:
		"""settle one reservation that will never be submitted."""
		entry = self._entries.get(reservation.message_id)
		if entry is None:
			return
		error = MessageReservationAbandonedError(
			f"message reservation {reservation.message_id} was abandoned"
		)
		if not entry.future.done():
			entry.future.set_exception(error)
		if not entry.processed.done():
			entry.processed.set_exception(error)

	def fail_all(self, error: BaseException) -> None:
		"""reject every unresolved reservation with one actor failure."""
		if self._failure is None:
			self._failure = error
		resolved_error = self._failure
		for entry in self._entries.values():
			if not entry.future.done():
				entry.future.set_exception(resolved_error)
			if not entry.processed.done():
				entry.processed.set_exception(resolved_error)

	def abandon_all(self) -> None:
		"""settle reservations never submitted before clean close."""
		for message_id, entry in list(self._entries.items()):
			if not entry.future.done():
				self.abandon(MessageReservation(message_id=message_id))

	def raise_if_failed(self) -> None:
		"""raise the actor failure as soon as execution can observe it."""
		if self._failure is not None:
			raise self._failure


@dataclass(frozen=True, slots=True)
class _CommittedOutput:
	"""what one committed write leaves the actor to act on."""

	receipt: MessageCommitReceipt
	"""the durable placement to hand every waiter on this message."""
	frame: bytes | None
	"""the ``message_created`` frame to publish; None when it could not build."""
	sets_container: bool
	"""whether this write chose the conversation the run answers in."""
	post_commit_error: BaseException | None
	"""delivery work that failed after the row was already durable."""


class RunOutputWriter:
	"""single-writer actor for generated run output."""

	def __init__(
		self,
		context: RunOutputContext,
		commit_tracker: MessageCommitTracker,
	) -> None:
		"""build the actor for one run, before its task is started."""
		self._context = context
		self._commit_tracker = commit_tracker
		self._queue: asyncio.Queue[RunOutputCommand] = asyncio.Queue()
		self._api_lock = asyncio.Lock()
		self._last_parent_id = context.initial_parent_id
		self._placement: OutputPlacement = (
			FirstOutputPlacement(splice=context.first_splice.model_copy(deep=True))
			if context.first_splice is not None
			else FollowingOutputPlacement()
		)
		self._replacement_committed = (
			not isinstance(self._placement, FirstOutputPlacement)
			or self._placement.splice.replaces is None
		)
		self._closing = False
		self._closed = False
		self._failure: BaseException | None = None
		self._abort_error: BaseException | None = None
		self._close_future: asyncio.Future[None] | None = None
		self._current_write: MessageReservation | None = None
		self._stopped = asyncio.get_running_loop().create_future()
		self._task = create_background_task(
			self._run(),
			name=f"run-output-writer:{context.run_id}",
		)
		self._task.add_done_callback(self._settle_stopped_actor)

	def reserve(self) -> MessageReservation:
		"""reserve an output id while the writer still accepts work."""
		self._raise_if_unavailable()
		return self._commit_tracker.reserve()

	@property
	def replacement_committed(self) -> bool:
		"""whether steering may enter the generated output sequence."""
		return self._replacement_committed

	async def submit(
		self,
		reservation: MessageReservation,
		message: SDKMessage,
		reply_to_message_id: TypeID | None,
		read_through_message_id: TypeID | None,
		citations: list[Citation],
	) -> None:
		"""enqueue one immutable completed-message snapshot."""
		self._raise_if_unavailable()
		command = WriteOutput(
			reservation=reservation,
			message=message.model_copy(deep=True),
			reply_to_message_id=reply_to_message_id,
			read_through_message_id=read_through_message_id,
			citations=tuple(item.model_copy(deep=True) for item in citations),
		)
		tool_call_ids = (
			tuple(tool_call.id for tool_call in message.tool_calls)
			if isinstance(message, SDKAssistantMessage)
			else ()
		)
		async with self._api_lock:
			self._raise_if_unavailable()
			self._commit_tracker.mark_submitted(reservation, tool_call_ids)
			self._queue.put_nowait(command)

	async def advance_parent(self, message_id: TypeID) -> ParentAdvanceReceipt:
		"""serialize a steering parent change after earlier output writes."""
		future = asyncio.get_running_loop().create_future()
		future.add_done_callback(observe_future_completion)
		command = AdvanceParent(parent_id=message_id, completion=future)
		await self._enqueue_public(command)
		return await asyncio.shield(future)

	async def barrier(self) -> BarrierReceipt:
		"""wait until every earlier command has completed."""
		future = asyncio.get_running_loop().create_future()
		future.add_done_callback(observe_future_completion)
		command = Barrier(completion=future)
		await self._enqueue_public(command)
		return await asyncio.shield(future)

	async def _enqueue_public(self, command: PublicRunOutputCommand) -> None:
		"""queue one caller command, refusing it if the actor is already done.

		the check and the put share the api lock so a writer that fails between
		them cannot accept a command nobody will ever run.
		"""
		async with self._api_lock:
			self._raise_if_unavailable()
			self._queue.put_nowait(command)

	async def finish(self) -> None:
		"""drain every prior command and stop, or raise the actor failure."""
		async with self._api_lock:
			if self._failure is not None:
				raise self._failure
			if self._close_future is None:
				self._closing = True
				self._close_future = asyncio.get_running_loop().create_future()
				self._close_future.add_done_callback(observe_future_completion)
				self._queue.put_nowait(Finish(completion=self._close_future))
			close_future = self._close_future
		await asyncio.shield(close_future)
		await asyncio.shield(self._stopped)

	async def abort(self, error: BaseException) -> None:
		"""stop the actor and settle every accepted or reserved output."""
		async with self._api_lock:
			if not self._task.done():
				self._closing = True
				self._abort_error = error
				self._task.cancel()
		async with asyncio.timeout(30):
			await asyncio.shield(self._stopped)

	def _raise_if_unavailable(self) -> None:
		"""reject work the actor can no longer carry out.

		a failure is raised in preference to the closed error: it says WHY the
		writer stopped taking work, which the caller reports.
		"""
		if self._failure is not None:
			raise self._failure
		if self._closing or self._closed:
			raise RunOutputWriterClosedError("run output writer is closed")

	async def _run(self) -> None:
		"""run queued commands in order until one fails or ``Finish`` arrives.

		the actor stops at the first failure rather than continuing: output is
		a chain, so a write that never landed makes every later placement a
		guess.
		"""
		while True:
			command = await self._queue.get()
			try:
				if isinstance(command, WriteOutput):
					await self._process_write(command)
				elif isinstance(command, AdvanceParent):
					self._last_parent_id = command.parent_id
					command.completion.set_result(
						ParentAdvanceReceipt(parent_id=command.parent_id)
					)
				elif isinstance(command, Barrier):
					command.completion.set_result(self._barrier_receipt())
				else:
					self._closed = True
					self._commit_tracker.abandon_all()
					command.completion.set_result(None)
					return
			except Exception as error:
				if isinstance(command, WriteOutput):
					self._commit_tracker.fail(command.reservation, error)
					self._current_write = None
				else:
					self._set_exception(command.completion, error)
				self._fail(error)
				return
			finally:
				self._queue.task_done()

	async def _process_write(self, command: WriteOutput) -> None:
		"""commit one output, then advance the run's state around it.

		the row is durable before any of the coordination below runs, so a
		failure here is reported against a message that already exists - the
		first such failure is raised and the rest only logged.
		"""
		self._current_write = command.reservation
		committed = await self._commit_write(command)
		self._last_parent_id = committed.receipt.message_id
		self._placement = FollowingOutputPlacement()
		self._replacement_committed = True
		self._commit_tracker.complete(command.reservation, committed.receipt)
		self._current_write = None

		post_commit_error = committed.post_commit_error
		if committed.sets_container:
			try:
				await run_conversations.set_container(
					self._context.run_id,
					committed.receipt.container_root_id,
				)
			except Exception as error:
				if post_commit_error is None:
					post_commit_error = error
				else:
					logger.exception("run container coordination also failed")
		if committed.frame is not None:
			try:
				await run_streams.publish(self._context.run_id, committed.frame)
			except Exception as error:
				if post_commit_error is None:
					post_commit_error = error
				else:
					logger.exception("message-created publication also failed")

		if post_commit_error is not None:
			raise post_commit_error.with_traceback(post_commit_error.__traceback__)
		self._commit_tracker.processed(command.reservation)

	async def _commit_write(self, command: WriteOutput) -> _CommittedOutput:
		"""write one generated message and report what its commit decided.

		a write that commits and then fails its delivery work still returns:
		the row exists, so the caller needs its placement rather than only the
		error.
		"""
		prepared = prepare_generated_message(
			command.message,
			sender_agent_id=self._context.agent_id,
			run_id=self._context.run_id,
			citations=list(command.citations),
			model_id=self._context.model_id,
		)
		prepared.draft.reply_to_message_id = command.reply_to_message_id
		pending_splice = (
			self._placement.splice
			if isinstance(self._placement, FirstOutputPlacement)
			else None
		)
		written = None
		post_commit_error: BaseException | None = None
		try:
			async with async_session_local() as session:
				if pending_splice is not None:
					prepared.draft.splice = pending_splice
				if pending_splice is not None or self._last_parent_id is None:
					written = await create_message_with_commit_outcome(
						self._context.thread_id,
						prepared.draft,
						session,
						self._context.principal,
						message_id=command.reservation.message_id,
						origin_session_id=self._context.origin_session_id,
						originated_resources=prepared.originated_resources,
					)
				else:
					run_tail_id = self._last_parent_id
					written = await create_message_at_run_tail_with_commit_outcome(
						self._context.thread_id,
						prepared.draft,
						run_tail_id=run_tail_id,
						run_id=self._context.run_id,
						session=session,
						principal=self._context.principal,
						message_id=command.reservation.message_id,
						origin_session_id=self._context.origin_session_id,
						read_through_message_id=command.read_through_message_id,
						originated_resources=prepared.originated_resources,
					)
		except CommittedMessageWriteError as error:
			written = error.written
			post_commit_error = error.cause

		if written is None:
			raise RuntimeError("message write returned no outcome")
		receipt = MessageCommitReceipt(
			message_id=written.message.id,
			parent_id=written.message.parent_id,
			container_root_id=written.container_root_id,
		)
		frame: bytes | None = None
		try:
			frame = sse_encode(
				event="message_created",
				data=message_created_frame_data(written.message, written.splice),
			)
		except Exception as error:
			if post_commit_error is None:
				post_commit_error = error
		return _CommittedOutput(
			receipt=receipt,
			frame=frame,
			sets_container=written.splice.leaf is not None,
			post_commit_error=post_commit_error,
		)

	def _barrier_receipt(self) -> BarrierReceipt:
		"""the writer state a barrier reports to whoever waited on it."""
		return BarrierReceipt(replacement_committed=self._replacement_committed)

	def _fail(self, error: BaseException) -> None:
		"""settle every waiter against the failure that stopped the actor.

		the first failure is the one reported: later ones are consequences of
		it, and a waiter told the wrong cause cannot act on it. nothing is left
		pending, since a caller awaiting a dead actor would hang.
		"""
		if self._failure is None:
			self._failure = error
		resolved_error = self._failure
		self._closing = True
		if self._current_write is not None:
			self._commit_tracker.fail(self._current_write, resolved_error)
			self._current_write = None
		self._commit_tracker.fail_all(resolved_error)
		while True:
			try:
				pending = self._queue.get_nowait()
			except asyncio.QueueEmpty:
				break
			if isinstance(pending, WriteOutput):
				self._commit_tracker.fail(pending.reservation, resolved_error)
			else:
				self._set_exception(pending.completion, resolved_error)
			self._queue.task_done()

	def _settle_stopped_actor(self, task: asyncio.Task[None]) -> None:
		"""close out the actor however its task ended.

		runs as the task's done callback, so it is the last chance to settle
		waiters: an actor that stopped without resolving them would hang every
		caller still awaiting a write.
		"""
		if task.cancelled() and self._abort_error is not None:
			create_background_task(
				self._reconcile_abort(self._abort_error),
				name=f"run-output-abort:{self._context.run_id}",
			)
			return
		if self._failure is None and not self._closed:
			error = (
				asyncio.CancelledError("run output writer was cancelled")
				if task.cancelled()
				else task.exception()
			)
			if error is not None:
				self._fail(error)
		if self._failure is not None and self._close_future is not None:
			self._set_exception(self._close_future, self._failure)
		if not self._stopped.done():
			self._stopped.set_result(None)

	async def _reconcile_abort(self, error: BaseException) -> None:
		"""find out whether the cancelled write landed, and settle it either way.

		a cancel can arrive after the commit but before its receipt, so the row
		is read back rather than assumed lost: reporting a persisted answer as
		failed would strand it in the conversation with nothing pointing at it.
		"""
		try:
			reservation = self._current_write
			if reservation is not None:
				async with async_session_local() as session:
					message = await session.get(Message, reservation.message_id)
					if message is not None:
						container_root_id = await branch_root_id(
							session,
							self._context.thread_id,
							message.id,
						)
						self._commit_tracker.complete(
							reservation,
							MessageCommitReceipt(
								message_id=message.id,
								parent_id=message.parent_id,
								container_root_id=container_root_id,
							),
						)
		finally:
			self._current_write = None
			self._fail(error)
			if self._close_future is not None:
				self._set_exception(self._close_future, error)
			if not self._stopped.done():
				self._stopped.set_result(None)

	@staticmethod
	def _set_exception(
		future: asyncio.Future[ParentAdvanceReceipt]
		| asyncio.Future[BarrierReceipt]
		| asyncio.Future[None],
		error: BaseException,
	) -> None:
		"""fail one waiter, unless something already settled it.

		the terminal paths overlap - a cancel can reach both the abort
		reconciler and the task callback - so settling twice is expected
		rather than a bug to raise on.
		"""
		if not future.done():
			future.set_exception(error)


def build_incomplete_assistant(
	current_assistant_id: TypeID | None,
	assistant: SDKAssistantMessage,
	finish_reason: FinishReason,
	allow_output: bool,
) -> SDKAssistantMessage | None:
	"""build persisted incomplete assistant output without side effects."""
	if current_assistant_id is None or (
		not assistant.content and not assistant.tool_calls
	):
		return None
	if not allow_output:
		return None
	partial = assistant.model_copy(deep=True)
	partial.finish_reason = finish_reason
	return partial
