import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import AssistantMessage as AssistantMessageORM
from api.models.message import Message as MessageORM
from api.models.thread import Thread
from api.schemas.message import Citation, CitationSource, MessageRange, MessageSplice
from api.tests.factories import create_user, make_principal, principal_for
from api.v1.service.runs import output_writer as writer_module
from api.v1.service.runs.contracts import SteeringInjection
from api.v1.service.runs.output_writer import (
	MessageCommitReceipt,
	MessageCommitTracker,
	MessageReservationAbandonedError,
	RunOutputContext,
	RunOutputWriter,
	RunOutputWriterClosedError,
	WriteOutput,
	build_incomplete_assistant,
)
from api.v1.service.runs.steering import QueuedSteering, SteeringFilter
from api.v1.service.threads.drafts import MessageDraft
from api.v1.service.threads.messages import writes as thread_message_writes
from api.v1.service.threads.messages.writes import CommittedMessageWriteError
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import ToolCall
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _make_writer() -> tuple[RunOutputWriter, MessageCommitTracker]:
	tracker = MessageCommitTracker()
	context = RunOutputContext(
		run_id=TypeID(new_typeid("run")),
		thread_id=TypeID(new_typeid("thread")),
		agent_id=TypeID(new_typeid("agent")),
		principal=make_principal(),
		origin_session_id=None,
		model_id=None,
		initial_parent_id=None,
		first_splice=None,
	)
	return RunOutputWriter(context, tracker), tracker


def _committed(command: WriteOutput) -> writer_module._CommittedOutput:
	receipt = MessageCommitReceipt(
		message_id=command.reservation.message_id,
		parent_id=None,
		container_root_id=None,
	)
	return writer_module._CommittedOutput(
		receipt=receipt,
		frame=None,
		sets_container=False,
		post_commit_error=None,
	)


@pytest.mark.asyncio
async def test_steering_filter_propagates_parent_commit_failure() -> None:
	failure = ValueError("parent write failed")
	injection = QueuedSteering(
		message_id=TypeID(new_typeid("msg")),
		message=SDKUserMessage.from_text("steer"),
	)

	async def claim() -> list[SteeringInjection]:
		return [injection]

	async def fail_on_injected(
		_injections: list[SteeringInjection],
	) -> list[SteeringInjection]:
		raise failure

	filter_ = SteeringFilter(
		claim=claim,
		on_injected=fail_on_injected,
	)
	state = AgentIterationState(thread=SDKThread(), tools=[])
	agent_context = AgentContext(
		model=ChatModel.model_construct(model_name="output-writer-test")
	)
	with pytest.raises(ValueError) as raised:
		await filter_.process(state, agent_context, None)
	assert raised.value is failure
	assert state.thread.messages == []


@pytest.mark.asyncio
async def test_steering_filter_settles_injection_before_propagating_cancellation() -> (
	None
):
	injection = QueuedSteering(
		message_id=TypeID(new_typeid("msg")),
		message=SDKUserMessage.from_text("steer"),
	)
	settlement_started = asyncio.Event()
	settlement_release = asyncio.Event()

	async def claim() -> list[SteeringInjection]:
		return [injection]

	async def settle(
		injections: list[SteeringInjection],
	) -> list[SteeringInjection]:
		settlement_started.set()
		await settlement_release.wait()
		return injections

	filter_ = SteeringFilter(claim=claim, on_injected=settle)
	state = AgentIterationState(thread=SDKThread(), tools=[])
	agent_context = AgentContext(
		model=ChatModel.model_construct(model_name="steering-cancellation-test")
	)
	processing = asyncio.create_task(filter_.process(state, agent_context, None))
	await settlement_started.wait()
	processing.cancel()
	await asyncio.sleep(0)
	assert not processing.done()

	settlement_release.set()
	with pytest.raises(asyncio.CancelledError):
		await processing
	assert state.thread.messages == [injection.message]


@pytest.mark.asyncio
async def test_steering_filter_defers_claim_until_replacement_commits() -> None:
	claimed = False
	ready = False

	async def claim() -> list[SteeringInjection]:
		nonlocal claimed
		claimed = True
		return []

	filter_ = SteeringFilter(claim=claim, ready=lambda: ready)
	state = AgentIterationState(thread=SDKThread(), tools=[])
	agent_context = AgentContext(
		model=ChatModel.model_construct(model_name="replacement-steering-test")
	)
	assert await filter_.process(state, agent_context, None) is state
	assert not claimed
	ready = True
	assert await filter_.process(state, agent_context, None) is state
	assert claimed


@pytest.mark.asyncio
async def test_empty_in_place_replacement_keeps_steering_deferred() -> None:
	tracker = MessageCommitTracker()
	context = RunOutputContext(
		run_id=TypeID(new_typeid("run")),
		thread_id=TypeID(new_typeid("thread")),
		agent_id=TypeID(new_typeid("agent")),
		principal=make_principal(),
		origin_session_id=None,
		model_id=None,
		initial_parent_id=None,
		first_splice=MessageSplice(
			parent_id=None,
			replaces=MessageRange(
				head_id=TypeID(new_typeid("msg")),
				tail_id=TypeID(new_typeid("msg")),
			),
		),
	)
	writer = RunOutputWriter(context, tracker)
	claimed = False

	async def claim() -> list[SteeringInjection]:
		nonlocal claimed
		claimed = True
		return []

	filter_ = SteeringFilter(claim=claim, ready=lambda: writer.replacement_committed)
	state = AgentIterationState(thread=SDKThread(), tools=[])
	agent_context = AgentContext(
		model=ChatModel.model_construct(model_name="empty-replacement-steering-test")
	)

	assert await filter_.process(state, agent_context, None) is state
	assert not claimed
	await writer.finish()
	assert not writer.replacement_committed


@pytest.mark.asyncio
async def test_thread_write_reports_committed_row_when_event_delivery_fails(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = principal_for(
		await create_user(db_session, "output_writer_post_commit", is_superuser=True)
	)
	thread_id = TypeID(new_typeid("thread"))
	message_id = TypeID(new_typeid("msg"))
	db_session.add(Thread(id=thread_id, owner_id=principal.user.id, tags=[]))
	await db_session.commit()
	failure = ValueError("fanout failed")

	async def fail_after_commit(*_args: object, **_kwargs: object) -> None:
		raise failure

	monkeypatch.setattr(
		thread_message_writes,
		"fanout_event",
		fail_after_commit,
	)
	draft = MessageDraft.from_sdk_message(SDKAssistantMessage.from_text("answer"))
	draft.splice = MessageSplice(parent_id=None)

	with pytest.raises(CommittedMessageWriteError) as raised:
		await thread_message_writes.create_message_with_commit_outcome(
			thread_id,
			draft,
			db_session,
			principal,
			message_id=message_id,
		)
	assert raised.value.written.message.id == message_id
	assert raised.value.cause is failure
	assert await db_session.get(MessageORM, message_id) is not None


def test_assistant_finish_reason_round_trips_through_persistence_models() -> None:
	draft = MessageDraft.from_sdk_message(
		SDKAssistantMessage.from_text("answer").model_copy(
			update={"finish_reason": "stop"}
		)
	)
	assert draft.finish_reason == "stop"
	message = AssistantMessageORM(
		thread_id=TypeID(new_typeid("thread")),
		content=[{"type": "text", "text": "answer"}],
		finish_reason=draft.finish_reason,
	)
	sdk_message = message.to_sdk()
	assert isinstance(sdk_message, SDKAssistantMessage)
	assert sdk_message.finish_reason == "stop"


@pytest.mark.asyncio
async def test_commit_signal_only_resolves_for_a_successful_commit() -> None:
	tracker = MessageCommitTracker()
	reservation = tracker.reserve()
	tracker.mark_submitted(reservation)
	event = Event(
		scope=EventScope.MESSAGE,
		scope_id=reservation.message_id,
		type=EventType.CITATION_SOURCES,
		data={},
		message_id=reservation.message_id,
	)
	correlation = asyncio.create_task(tracker.correlate_event(event))
	await asyncio.sleep(0)
	assert not correlation.done()

	receipt = MessageCommitReceipt(
		message_id=reservation.message_id,
		parent_id=None,
		container_root_id=None,
	)
	tracker.complete(reservation, receipt)
	await correlation
	assert event.message_id == reservation.message_id
	assert await tracker.require_committed(reservation.message_id) == receipt
	processed = asyncio.create_task(tracker.require_processed(reservation.message_id))
	await asyncio.sleep(0)
	assert not processed.done()
	tracker.processed(reservation)
	await processed


@pytest.mark.asyncio
async def test_failed_commit_clears_event_correlation_and_propagates_parent_error() -> (
	None
):
	tracker = MessageCommitTracker()
	reservation = tracker.reserve()
	tracker.mark_submitted(reservation)
	failure = ValueError("write failed")
	tracker.fail(reservation, failure)
	event = Event(
		scope=EventScope.MESSAGE,
		scope_id=reservation.message_id,
		type=EventType.CITATION_SOURCES,
		data={},
		message_id=reservation.message_id,
	)

	await tracker.correlate_event(event)
	assert event.message_id is None
	with pytest.raises(ValueError) as raised:
		await tracker.require_committed(reservation.message_id)
	assert raised.value is failure


@pytest.mark.asyncio
async def test_tool_event_resolves_its_assistant_message_from_tool_call_id(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, tracker = _make_writer()

	async def commit(command: WriteOutput) -> writer_module._CommittedOutput:
		return _committed(command)

	monkeypatch.setattr(writer, "_commit_write", commit)
	tool_call = ToolCall(name="search", arguments={})
	reservation = writer.reserve()
	await writer.submit(
		reservation,
		SDKAssistantMessage(tool_calls=[tool_call], finish_reason="tool_calls"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	event = Event(
		scope=EventScope.THREAD,
		type=EventType.TOOL_PROGRESS,
		data={"tool_call_id": tool_call.id},
	)
	await tracker.correlate_event(event)
	assert event.message_id == reservation.message_id
	await writer.finish()


@pytest.mark.asyncio
async def test_close_drains_writes_and_captures_citation_snapshot(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, tracker = _make_writer()
	gate = asyncio.Event()
	captured: list[WriteOutput] = []

	async def commit(command: WriteOutput) -> writer_module._CommittedOutput:
		await gate.wait()
		captured.append(command)
		return _committed(command)

	monkeypatch.setattr(writer, "_commit_write", commit)
	reservation = writer.reserve()
	citation = Citation(
		index=1,
		source_type=CitationSource.URL,
		source_id="https://example.com/original",
		title="original",
	)
	citations = [citation]
	await writer.submit(
		reservation,
		SDKAssistantMessage.from_text("answer"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=citations,
	)
	citation.source_id = "https://example.com/mutated"
	citations.append(
		Citation(
			index=2,
			source_type=CitationSource.URL,
			source_id="https://example.com/later",
		)
	)
	close_task = asyncio.create_task(writer.finish())
	await asyncio.sleep(0)
	assert not close_task.done()

	gate.set()
	await close_task
	assert len(captured[0].citations) == 1
	assert captured[0].citations[0].source_id == "https://example.com/original"
	assert await tracker.require_committed(reservation.message_id) is not None


@pytest.mark.asyncio
async def test_cancelled_finish_waiter_does_not_cancel_writer(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, tracker = _make_writer()
	gate = asyncio.Event()

	async def commit(command: WriteOutput) -> writer_module._CommittedOutput:
		await gate.wait()
		return _committed(command)

	monkeypatch.setattr(writer, "_commit_write", commit)
	reservation = writer.reserve()
	await writer.submit(
		reservation,
		SDKAssistantMessage.from_text("answer"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	waiter = asyncio.create_task(writer.finish())
	await asyncio.sleep(0)
	waiter.cancel()
	with pytest.raises(asyncio.CancelledError):
		await waiter
	gate.set()
	await writer.finish()
	assert tracker.committed(reservation)


@pytest.mark.asyncio
async def test_parent_advancement_is_ordered_between_output_writes(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, _tracker = _make_writer()
	observed: list[tuple[TypeID, TypeID | None]] = []
	first_write_started = asyncio.Event()
	release_first_write = asyncio.Event()

	async def commit(command: WriteOutput) -> writer_module._CommittedOutput:
		if not observed:
			first_write_started.set()
			await release_first_write.wait()
		observed.append((command.reservation.message_id, writer._last_parent_id))
		return _committed(command)

	monkeypatch.setattr(writer, "_commit_write", commit)
	first = writer.reserve()
	await writer.submit(
		first,
		SDKAssistantMessage.from_text("first"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	steering_parent = TypeID(new_typeid("msg"))
	advance_task = asyncio.create_task(writer.advance_parent(steering_parent))
	await asyncio.sleep(0)
	assert first_write_started.is_set()
	assert not advance_task.done()
	release_first_write.set()
	advance = await advance_task
	assert advance.parent_id == steering_parent

	second = writer.reserve()
	await writer.submit(
		second,
		SDKAssistantMessage.from_text("second"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	await writer.finish()
	assert observed == [
		(first.message_id, writer._context.initial_parent_id),
		(second.message_id, steering_parent),
	]


@pytest.mark.asyncio
async def test_commands_after_failure_propagate_the_original_error(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, tracker = _make_writer()
	failure = ValueError("database unavailable")
	release_failure = asyncio.Event()

	async def fail_commit(_command: WriteOutput) -> writer_module._CommittedOutput:
		await release_failure.wait()
		raise failure

	monkeypatch.setattr(writer, "_commit_write", fail_commit)
	reservation = writer.reserve()
	pending_reservation = writer.reserve()
	await writer.submit(
		reservation,
		SDKAssistantMessage.from_text("answer"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	await writer.submit(
		pending_reservation,
		SDKAssistantMessage.from_text("pending"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	advance_task = asyncio.create_task(writer.advance_parent(TypeID(new_typeid("msg"))))
	await asyncio.sleep(0)
	release_failure.set()
	with pytest.raises(ValueError) as committed:
		await tracker.require_committed(reservation.message_id)
	assert committed.value is failure
	with pytest.raises(ValueError) as pending:
		await tracker.require_committed(pending_reservation.message_id)
	assert pending.value is failure
	with pytest.raises(ValueError) as advance:
		await advance_task
	assert advance.value is failure
	with pytest.raises(ValueError) as barrier:
		await writer.barrier()
	assert barrier.value is failure
	with pytest.raises(ValueError) as reserve:
		writer.reserve()
	assert reserve.value is failure
	with pytest.raises(ValueError) as close:
		await writer.finish()
	assert close.value is failure


@pytest.mark.asyncio
async def test_post_commit_failure_keeps_commit_signal_and_fails_writer(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, tracker = _make_writer()
	failure = ValueError("fanout failed")
	published = asyncio.Event()

	async def publish(_run_id: TypeID, _frame: bytes) -> None:
		published.set()

	monkeypatch.setattr(writer_module.run_streams, "publish", publish)

	async def committed_then_failed(
		command: WriteOutput,
	) -> writer_module._CommittedOutput:
		committed = _committed(command)
		return writer_module._CommittedOutput(
			receipt=committed.receipt,
			frame=b"message-created",
			sets_container=False,
			post_commit_error=failure,
		)

	monkeypatch.setattr(writer, "_commit_write", committed_then_failed)
	reservation = writer.reserve()
	await writer.submit(
		reservation,
		SDKAssistantMessage.from_text("answer"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	event = Event(
		scope=EventScope.MESSAGE,
		scope_id=reservation.message_id,
		type=EventType.CITATION_SOURCES,
		data={},
		message_id=reservation.message_id,
	)
	correlation = asyncio.create_task(tracker.correlate_event(event))
	committed = await tracker.require_committed(reservation.message_id)
	assert committed is not None
	assert committed.message_id == reservation.message_id
	assert published.is_set()
	await correlation
	assert event.message_id == reservation.message_id
	assert tracker.committed(reservation)
	with pytest.raises(ValueError) as close:
		await writer.finish()
	assert close.value is failure
	with pytest.raises(ValueError) as processed:
		await tracker.require_processed(reservation.message_id)
	assert processed.value is failure


@pytest.mark.asyncio
async def test_processed_signal_waits_for_message_created_publish(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, tracker = _make_writer()
	publish_started = asyncio.Event()
	release_publish = asyncio.Event()

	async def publish(_run_id: TypeID, _frame: bytes) -> None:
		publish_started.set()
		await release_publish.wait()

	async def commit(command: WriteOutput) -> writer_module._CommittedOutput:
		committed = _committed(command)
		return writer_module._CommittedOutput(
			receipt=committed.receipt,
			frame=b"message-created",
			sets_container=False,
			post_commit_error=None,
		)

	monkeypatch.setattr(writer_module.run_streams, "publish", publish)
	monkeypatch.setattr(writer, "_commit_write", commit)
	reservation = writer.reserve()
	await writer.submit(
		reservation,
		SDKAssistantMessage.from_text("answer"),
		reply_to_message_id=None,
		read_through_message_id=None,
		citations=[],
	)
	await publish_started.wait()
	assert await tracker.require_committed(reservation.message_id) is not None
	processed = asyncio.create_task(tracker.require_processed(reservation.message_id))
	await asyncio.sleep(0)
	assert not processed.done()

	release_publish.set()
	await processed
	await writer.finish()


@pytest.mark.asyncio
async def test_close_abandons_reservations_and_rejects_later_commands() -> None:
	writer, tracker = _make_writer()
	reservation = writer.reserve()
	event = Event(
		scope=EventScope.MESSAGE,
		scope_id=reservation.message_id,
		type=EventType.CITATION_SOURCES,
		data={},
		message_id=reservation.message_id,
	)
	correlation = asyncio.create_task(tracker.correlate_event(event))
	await writer.finish()
	await correlation

	with pytest.raises(MessageReservationAbandonedError):
		await tracker.require_committed(reservation.message_id)
	assert event.message_id is None
	with pytest.raises(RunOutputWriterClosedError):
		writer.reserve()
	with pytest.raises(RunOutputWriterClosedError):
		await writer.submit(
			reservation,
			SDKAssistantMessage.from_text("late"),
			reply_to_message_id=None,
			read_through_message_id=None,
			citations=[],
		)
	with pytest.raises(RunOutputWriterClosedError):
		await writer.advance_parent(TypeID(new_typeid("msg")))
	with pytest.raises(RunOutputWriterClosedError):
		await writer.barrier()


@pytest.mark.asyncio
async def test_abort_fails_reserved_outputs_and_stops_actor() -> None:
	writer, tracker = _make_writer()
	reservation = writer.reserve()
	failure = RuntimeError("output deadline expired")
	await writer.abort(failure)

	with pytest.raises(RuntimeError) as committed:
		await tracker.require_committed(reservation.message_id)
	assert committed.value is failure
	with pytest.raises(RuntimeError) as reserve:
		writer.reserve()
	assert reserve.value is failure


@pytest.mark.asyncio
async def test_abort_reconciliation_failure_still_stops_actor(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	writer, tracker = _make_writer()
	reservation = writer.reserve()
	writer._current_write = reservation
	failure = RuntimeError("output deadline expired")
	monkeypatch.setattr(
		writer_module,
		"async_session_local",
		lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
	)

	await writer.abort(failure)

	with pytest.raises(RuntimeError) as committed:
		await tracker.require_committed(reservation.message_id)
	assert committed.value is failure


def test_incomplete_builder_keeps_output_without_metadata() -> None:
	message_id = TypeID(new_typeid("msg"))
	assistant = SDKAssistantMessage.from_text("partial answer")
	assert (
		build_incomplete_assistant(
			current_assistant_id=message_id,
			assistant=assistant,
			finish_reason="cancelled",
			allow_output=False,
		)
		is None
	)

	partial = build_incomplete_assistant(
		current_assistant_id=message_id,
		assistant=assistant,
		finish_reason="error",
		allow_output=True,
	)
	assert partial is not None
	assert partial.text == "partial answer"
	assert partial.finish_reason == "error"
	assert partial.metadata is None
