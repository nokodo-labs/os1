"""agent run execution logic."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Mapping

from fastapi import HTTPException

from api.database import async_session_local, safe_rollback
from api.local_tasks import create_background_task
from api.schemas.common import MISSING, unwrap_missing
from api.schemas.message import (
	BranchLeaf,
	Citation,
	MessageCreate,
	MessageRange,
	MessageSplice,
	RunBlockRef,
	ThreadLeaf,
)
from api.schemas.runs import ClientContext, ToolChoice
from api.settings import settings as app_settings
from api.v1.service.activities import ActivityEmitter, start_activity
from api.v1.service.agents.runtime import (
	build_agent_from_orm,
	load_agent_for_run,
)
from api.v1.service.authentication import Principal, load_principal_for_user
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.message_metadata import (
	MESSAGE_ID_KEY,
	strip_private_sdk_metadata,
)
from api.v1.service.chat.message_references import (
	new_message_reference,
	reject_message_reference,
	resolve_message_reference,
)
from api.v1.service.chat.messages import (
	build_run_input_sdk_user_message,
	inject_system_instructions,
	load_sdk_thread_before_message,
)
from api.v1.service.chat.thread_maintenance import schedule_post_run_thread_upkeep
from api.v1.service.embeddings import embed_text
from api.v1.service.events import (
	build_live_persisting_event_emitter,
	build_live_user_event_emitter,
)
from api.v1.service.runs.access_cursors import (
	initialize_thread_access_cursor,
	release_thread_access_cursor,
)
from api.v1.service.runs.bus import RunRoute, register_run_route
from api.v1.service.runs.contracts import PersistedRunInput
from api.v1.service.runs.failures import (
	RunFailureReason,
	broadcast_run_failure,
	schedule_terminate_broadcast,
	terminate_run,
)
from api.v1.service.runs.notify import notify_agent_answer
from api.v1.service.runs.output_writer import (
	MessageCommitTracker,
	MessageReservation,
	RunOutputContext,
	RunOutputWriter,
	build_incomplete_assistant,
)
from api.v1.service.runs.status import (
	ReplyAnchorReservation,
	broadcast_run_event,
	run_conversations,
	run_inbox,
	run_registry,
	run_streams,
)
from api.v1.service.runs.steering import (
	prepare_steering,
	remote_steering_injection,
	settle_remote_invocation,
	settle_remote_steering_drop,
)
from api.v1.service.runs.steering_bus import (
	CancelRunCommand,
	DropSteeringCommand,
	InvocationSteeringCommand,
	SteeringCommand,
	start_steering_subscriber,
)
from api.v1.service.runs.thread_context import resolve_run_thread
from api.v1.service.threads import branch_root_id
from api.v1.service.threads.common import thread_head_id
from nokodo_ai.adapters.chat import GenerationError as SDKGenerationError
from nokodo_ai.deltas import AgentDelta
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.types.sentinels import MissingType
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)


async def run_agent(
	thread_id: TypeID | None,
	agent_id: TypeID,
	principal: Principal,
	input: MessageCreate | None = None,
	splice: MessageSplice | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	persist: bool = True,
	tool_choice: ToolChoice | None = None,
	extra_plugins: list[str] | None = None,
	run_id_override: TypeID | None = None,
	ready_event: asyncio.Event | None = None,
	registered_event: asyncio.Event | None = None,
	invoking_message_id: TypeID | None = None,
	persisted_input: PersistedRunInput | None = None,
) -> None:
	"""execute a thread run and publish its sse events.

	when ``persist`` is True (default) full DB persistence is applied:
	messages are saved, run status is tracked, and metadata is generated.

	when ``invoking_message_id`` is provided the run answers a mention that is
	already persisted: it is the run's starting snapshot, the anchor its first
	answer replies to, and the boundary a later mention catches it up from.

	when ``persist`` is False an ephemeral inference is performed:
	no thread, messages, or metadata are written to the database.
	``thread_id`` may be None in this case; ``input`` must be provided.

	when ``run_id_override`` is provided, the caller has already allocated the
	run id (used for background-task execution where the caller needs
	the id before this generator starts publishing).

	when ``ready_event`` is provided, it is set once the run is registered and
	bound to its conversation. callers driving this
	generator as a background task can wait on this event before subscribing to
	the store, guaranteeing they will not miss any frames, and invocation
	waiters can steer the run knowing it will resolve their mention correctly.

	each SSE ``delta`` event includes:
	- run_id: stable ID for this run
	- message_id: stable ID for the currently streaming message
	- splice: placement for the first delta of each message
	- delta: the raw AgentDelta payload (Pydantic JSON)
	"""
	run_id = run_id_override if run_id_override is not None else new_typeid("run")
	parent_id: TypeID | None | MissingType = (
		splice.parent_id if splice is not None else MISSING
	)

	async with async_session_local() as session:
		replacement_head_id: TypeID | None = (
			splice.replaces.run_head_message_id
			if splice is not None and isinstance(splice.replaces, RunBlockRef)
			else (
				splice.replaces.head_id
				if splice is not None and isinstance(splice.replaces, MessageRange)
				else None
			)
		)
		context_parent_id: TypeID | None | MissingType = parent_id
		initial_parent_id: TypeID | None = None
		conversation_container_root_id: TypeID | None = None
		resolved_input_message: SDKUserMessage | None = None

		# register run in status store + (when on a thread) broadcast
		# run.started. ``persist`` only gates DB writes (messages, metadata);
		# every run lives in the registry so it is cancellable, observable,
		# and resumable regardless of whether we persist its outputs.
		async def _handle_steering_command(command: SteeringCommand) -> None:
			if isinstance(command, CancelRunCommand):
				await run_registry.cancel_run(run_id, reason=command.reason)
				return
			if isinstance(command, DropSteeringCommand):
				if await run_inbox.drop_pending_steering(run_id, command.message_id):
					create_background_task(
						settle_remote_steering_drop(run_id, command),
						name=f"settle-remote-steering-drop:{run_id}",
					)
				return
			if isinstance(command, InvocationSteeringCommand):
				async with async_session_local() as steering_session:
					steering_principal = await load_principal_for_user(
						principal.user.id,
						steering_session,
					)
					result = await settle_remote_invocation(
						run_id,
						command.message_id,
						steering_principal,
						steering_session,
					)
					if result.state == "dropped" and thread_id is not None:
						await broadcast_run_failure(
							thread_id=thread_id,
							agent_id=agent_id,
							reason=RunFailureReason.NOT_DELIVERED,
							anchor_message_id=command.message_id,
							run_id=run_id,
						)
				return
			accepted = await run_inbox.enqueue(
				run_id,
				remote_steering_injection(command),
			)
			if not accepted and command.retractable:
				create_background_task(
					settle_remote_steering_drop(
						run_id,
						DropSteeringCommand(
							message_id=command.message_id,
							thread_id=command.thread_id,
							agent_id=command.agent_id,
						),
					),
					name=f"settle-refused-remote-steering:{run_id}",
				)

		await run_registry.start_run(
			run_id=run_id,
			agent_id=agent_id,
			user_id=principal.user.id,
			thread_id=thread_id,
			persist=persist,
		)
		if registered_event is not None:
			registered_event.set()
		if thread_id is not None:
			await initialize_thread_access_cursor(thread_id)
		# self-attach the producer task so cancel_run works from the very
		# first microsecond the run is visible. when this generator is
		# being driven by a background task (the normal path), current_task()
		# IS that producer; when it is driven inline by an HTTP request
		# (legacy / tests), there is no producer to cancel and the attach
		# becomes a no-op via cancel_run's task.done() guard.
		current = asyncio.current_task()
		if current is not None:
			await run_registry.attach_task(run_id, current)
		if persist and persisted_input is not None:
			assert thread_id is not None  # persist=True requires a thread_id
			resolved_input_message = persisted_input.sdk_message
			frame = sse_encode(
				event="message_created",
				data=persisted_input.created_frame,
			)
			await run_streams.publish(run_id, frame)
			initial_parent_id = persisted_input.message_id
			context_parent_id = persisted_input.message_id
			conversation_container_root_id = persisted_input.container_root_id
			await run_conversations.bind(
				run_id,
				container_root_id=conversation_container_root_id,
				invocation_message_id=persisted_input.message_id,
			)
		elif persist and invoking_message_id is not None:
			assert thread_id is not None  # persist=True requires a thread_id
			# the mention is already in the conversation: it is where this run
			# starts reading, and what its first answer replies to.
			initial_parent_id = invoking_message_id
			context_parent_id = invoking_message_id
			conversation_container_root_id = await branch_root_id(
				session, thread_id, invoking_message_id
			)
			await run_conversations.bind(
				run_id,
				container_root_id=conversation_container_root_id,
				invocation_message_id=invoking_message_id,
			)
		else:
			if input is not None:
				resolved_input_message = build_run_input_sdk_user_message(input)
			initial_parent_id = unwrap_missing(parent_id)
			if persist and thread_id is not None:
				# regeneration answers no message, but it still starts from a
				# snapshot: without that boundary the first mention would hand
				# the agent the entire branch it was just loaded with. the
				# snapshot is knowable here without loading it - resolving it
				# after the branch load would leave the whole startup window
				# accepting catch-ups measured from nothing.
				container_message_id = (
					replacement_head_id
					if replacement_head_id is not None
					else (parent_id if isinstance(parent_id, TypeID) else None)
				)
				conversation_container_root_id = (
					await branch_root_id(
						session,
						thread_id,
						container_message_id,
					)
					if container_message_id is not None
					else None
				)
				head_id = await thread_head_id(session, thread_id)
				if replacement_head_id is not None:
					# the run reads context ending before the replaced head,
					# and owns everything from it onward.
					read_through_message_id = replacement_head_id
				elif parent_id is not MISSING:
					# an explicit parent is the snapshot, including an explicit
					# None, which starts the run from an empty conversation.
					read_through_message_id = unwrap_missing(parent_id)
				else:
					read_through_message_id = head_id
				await run_conversations.bind(
					run_id,
					container_root_id=conversation_container_root_id,
					invocation_message_id=None,
					read_through_message_id=read_through_message_id,
					anchor_message_id=read_through_message_id or head_id,
				)
		if not persist and thread_id is not None:
			context_message_id = parent_id if isinstance(parent_id, TypeID) else None
			conversation_container_root_id = (
				await branch_root_id(session, thread_id, context_message_id)
				if context_message_id is not None
				else None
			)
			# writing nothing does not mean failing invisibly: this run answers
			# a real conversation, so its durable failure needs the same anchor
			# a persisted run's would have.
			await run_conversations.bind(
				run_id,
				container_root_id=conversation_container_root_id,
				invocation_message_id=None,
				read_through_message_id=context_message_id,
				anchor_message_id=(
					context_message_id or await thread_head_id(session, thread_id)
				),
			)
		steering_subscriber = await start_steering_subscriber(
			run_id,
			_handle_steering_command,
		)
		await run_registry.attach_steering_task(run_id, steering_subscriber)
		await register_run_route(
			run_id,
			RunRoute(
				thread_id=thread_id,
				container_root_id=conversation_container_root_id,
				agent_id=agent_id,
				user_id=principal.user.id,
				persist=persist,
			),
		)

		# announced only once the run knows which conversation it answers and
		# where it starts reading: a waiter released earlier would steer a run
		# with no container and no catch-up boundary.
		if thread_id is not None:
			create_background_task(
				broadcast_run_event(
					thread_id=thread_id,
					agent_id=agent_id,
					run_id=run_id,
					started=True,
				),
				name="broadcast_run_started",
			)
		if ready_event is not None:
			ready_event.set()

		current_assistant_id: TypeID | None = None
		assistant_accum = SDKAssistantMessage()
		try:
			agent = await load_agent_for_run(agent_id, session, principal)
		except HTTPException:
			raise
		except Exception:
			logger.exception("failed to load agent")
			await terminate_run(run_id, reason="generation failed")
			return

		first_output_splice = (
			splice if input is None and invoking_message_id is None else None
		)
		model_id_for_persist: str | None = str(agent.model.id) if agent.model else None

		commit_tracker: MessageCommitTracker | None = None
		output_writer: RunOutputWriter | None = None
		citations: list[Citation]
		if persist:
			assert thread_id is not None  # persist=True requires a thread_id
			commit_tracker = MessageCommitTracker()
			emitter = build_live_persisting_event_emitter(
				before_persist=commit_tracker.correlate_event,
				on_emit=lambda: run_streams.touch_run(run_id),
			)
			citations = []
		else:
			# ephemeral means nothing durable, not nothing visible: the
			# requester still watches its own run work, so tool progress and
			# activity reach their sockets and are never written down.
			emitter = build_live_user_event_emitter(principal.user.id)
			citations = []

		final_assistant_message_ref = new_message_reference() if persist else None

		async def _start_activity(
			activity_type: str,
			message_id: TypeID | str | None,
			title: str | None = None,
			message: str | None = None,
			data: Mapping[str, object] | None = None,
		) -> ActivityEmitter | None:
			return await start_activity(
				emitter,
				user_id=str(principal.user.id),
				thread_id=thread_id,
				run_id=run_id,
				activity_type=activity_type,
				message_id=message_id,
				title=title,
				message=message,
				data=data,
			)

		ctx = AppContext(
			session=session,
			principal=principal,
			run_id=run_id,
			agent_id=agent_id,
			thread_id=thread_id,
			final_assistant_message_ref=final_assistant_message_ref,
			event_emitter=emitter,
			context_window=(agent.model.context_window if agent.model else None),
			citations=citations,
			start_activity=_start_activity,
			has_in_flight_input=lambda: run_inbox.has_in_flight_steering(run_id),
		)

		try:
			sdk_agent = await build_agent_from_orm(agent, ctx, extra_plugins)
		except Exception:
			logger.exception("failed to build agent")
			await terminate_run(run_id, reason="generation failed")
			return

		if persist:
			assert thread_id is not None  # persist=True requires a thread_id
			if replacement_head_id is not None:
				thread, resolved_head = await load_sdk_thread_before_message(
					thread_id,
					replacement_head_id,
					session,
					principal,
				)
				thread = await inject_system_instructions(
					agent,
					thread,
					session=session,
					principal=principal,
					client_context=client_context,
				)
			else:
				thread, resolved_head = await resolve_run_thread(
					agent,
					session,
					principal,
					thread_id=thread_id,
					initial_parent_id=context_parent_id,
					resolved_input_message=resolved_input_message,
					client_context=client_context,
					persist=persist,
				)
		else:
			thread, _resolved_head = await resolve_run_thread(
				agent,
				session,
				principal,
				thread_id=thread_id,
				initial_parent_id=context_parent_id,
				resolved_input_message=resolved_input_message,
				client_context=client_context,
				persist=False,
			)
		if persist and resolved_head is not None:
			initial_parent_id = resolved_head

		# build retrieval context explicitly before the agent/filter loop.
		# filters read from ctx.retrieval rather than computing their own.
		# when retrieval_pre_build is False, each filter builds its own query.
		if app_settings.ai.retrieval_pre_build:
			turns = thread.recent_turns(app_settings.ai.retrieval_turns)
			if turns:
				ctx.retrieval.query_text = "\n".join(turns)
				ctx.retrieval.query_embedding = await embed_text(
					text=ctx.retrieval.query_text, session=session, input_type="query"
				)

		streaming_parent_id: TypeID | None = initial_parent_id
		streaming_splice = first_output_splice
		if streaming_splice is None:
			streaming_leaf = None
			if persist and thread_id is not None:
				streaming_leaf = (
					BranchLeaf(kind="branch", root_id=conversation_container_root_id)
					if conversation_container_root_id is not None
					else ThreadLeaf(kind="thread")
				)
			streaming_splice = MessageSplice(
				parent_id=streaming_parent_id,
				leaf=streaming_leaf,
			)
		streaming_splice_data = streaming_splice.model_dump(mode="json")
		last_completed_assistant_id: TypeID | None = None
		current_assistant_reservation: MessageReservation | None = None
		splice_pending = True

		if commit_tracker is not None:
			assert thread_id is not None  # persist=True requires a thread_id
			output_writer = RunOutputWriter(
				context=RunOutputContext(
					run_id=run_id,
					thread_id=thread_id,
					agent_id=agent_id,
					principal=principal,
					origin_session_id=origin_session_id,
					model_id=model_id_for_persist,
					initial_parent_id=initial_parent_id,
					first_splice=first_output_splice,
				),
				commit_tracker=commit_tracker,
			)

		async def _advance_parent_after_steering(message_id: TypeID) -> None:
			"""advance streaming and persistence parents after steering injection."""
			nonlocal streaming_parent_id, streaming_splice, streaming_splice_data
			assert streaming_splice is not None
			if output_writer is not None:
				await output_writer.advance_parent(message_id)
			streaming_parent_id = message_id
			if streaming_splice.replaces is None:
				streaming_splice = streaming_splice.model_copy(
					update={"parent_id": message_id}
				)
				streaming_splice_data = streaming_splice.model_dump(mode="json")

		def _steering_ready() -> bool:
			return output_writer is None or output_writer.replacement_committed

		async def _require_processed_parent(message_id: TypeID | None) -> None:
			"""require a tracked output parent to finish run coordination."""
			if commit_tracker is not None:
				await commit_tracker.require_processed(message_id)

		async def _settle_final_assistant_reference() -> None:
			if final_assistant_message_ref is None:
				return
			if last_completed_assistant_id is not None and commit_tracker is not None:
				try:
					await commit_tracker.require_committed(last_completed_assistant_id)
				except Exception:
					pass
				else:
					await resolve_message_reference(
						final_assistant_message_ref,
						last_completed_assistant_id,
					)
					return
			await reject_message_reference(
				final_assistant_message_ref,
				"no_final_assistant_message",
			)

		async def _reserve_output_context() -> tuple[
			ReplyAnchorReservation | None,
			TypeID | None,
		]:
			return (
				await run_conversations.reserve_reply_anchor(run_id),
				await run_conversations.read_through(run_id),
			)

		async def _submit_output(
			reservation: MessageReservation,
			message: SDKMessage,
			include_reply_anchor: bool,
		) -> None:
			if output_writer is None:
				return
			anchor: ReplyAnchorReservation | None = None
			submitted = False
			try:
				if include_reply_anchor:
					anchor, read_through_message_id = await _reserve_output_context()
				else:
					read_through_message_id = await run_conversations.read_through(
						run_id
					)
				await output_writer.submit(
					reservation,
					message,
					reply_to_message_id=(
						anchor.message_id if anchor is not None else None
					),
					read_through_message_id=read_through_message_id,
					citations=citations,
				)
				submitted = True
			except BaseException:
				if anchor is not None and not submitted:
					await run_conversations.release_reply_anchor(run_id, anchor)
				raise
			if anchor is None or commit_tracker is None:
				return

			async def _settle_anchor() -> None:
				try:
					await commit_tracker.require_committed(reservation.message_id)
				except Exception:
					await run_conversations.release_reply_anchor(run_id, anchor)
					raise
				await run_conversations.acknowledge_reply_anchor(run_id, anchor)

			settlement = create_background_task(
				_settle_anchor(),
				name=f"run-reply-anchor:{run_id}:{reservation.message_id}",
			)
			await asyncio.shield(settlement)

		async def _finish_output_writer() -> None:
			if output_writer is None:
				return
			try:
				async with asyncio.timeout(30):
					await output_writer.finish()
			except asyncio.CancelledError:
				raise
			except BaseException as error:
				await output_writer.abort(error)
				raise

		async def _await_finalizer[T](operation: Awaitable[T], name: str) -> T:
			async def _run_operation() -> T:
				return await operation

			task = create_background_task(_run_operation(), name=name)
			deadline = asyncio.get_running_loop().time() + 30
			cancelled = False
			while True:
				remaining = deadline - asyncio.get_running_loop().time()
				if remaining <= 0:
					task.cancel()
					logger.error("run finalizer timed out", extra={"name": name})
					raise TimeoutError(name)
				try:
					result = await asyncio.wait_for(asyncio.shield(task), remaining)
				except asyncio.CancelledError:
					# the finalizer is shielded so it can land, but a cancel
					# aimed at this run still ends it: absorbing one here
					# reports a clean completion for a run asked to stop.
					cancelled = True
					if task.done():
						raise
				except TimeoutError:
					task.cancel()
					logger.error("run finalizer timed out", extra={"name": name})
					raise
				else:
					if cancelled:
						raise asyncio.CancelledError
					return result

		async def _settle_output() -> TypeID | None:
			"""submit eligible incomplete output and fail closed while draining."""
			if output_writer is None:
				return None
			partial_reservation: MessageReservation | None = None
			try:
				async with asyncio.timeout(30):
					if current_assistant_reservation is None or (
						commit_tracker is not None
						and commit_tracker.submitted(current_assistant_reservation)
					):
						await output_writer.finish()
						return None
					barrier = await output_writer.barrier()
					partial = build_incomplete_assistant(
						current_assistant_id=current_assistant_id,
						assistant=assistant_accum,
						allow_output=barrier.replacement_committed,
					)
					partial_reservation = (
						current_assistant_reservation if partial is not None else None
					)
					if (
						partial is None
						and current_assistant_reservation is not None
						and commit_tracker is not None
					):
						commit_tracker.abandon(current_assistant_reservation)
					if partial is not None:
						if partial_reservation is None:
							raise RuntimeError("partial output has no reservation")
						await _submit_output(
							partial_reservation,
							partial,
							include_reply_anchor=True,
						)
					await output_writer.finish()
			except BaseException as error:
				await output_writer.abort(error)
				raise
			if partial_reservation is None or commit_tracker is None:
				return None
			return (
				partial_reservation.message_id
				if commit_tracker.committed(partial_reservation)
				else None
			)

		try:
			run_agent_instance = await prepare_steering(
				principal=principal,
				run_id=run_id,
				sdk_agent=sdk_agent,
				thread_id=thread_id,
				agent_id=agent_id,
				parent_id_provider=lambda: streaming_parent_id,
				require_processed=(
					_require_processed_parent if commit_tracker is not None else None
				),
				advance_parent=_advance_parent_after_steering,
				ready=_steering_ready,
			)

			stream = await run_agent_instance.run(
				thread,
				app_context=ctx,
				tool_choice=tool_choice or "auto",
				stream=True,
			)
			await session.close()

			def _reserve_message() -> MessageReservation:
				"""allocate a streamed message id."""
				if output_writer is not None:
					return output_writer.reserve()
				return MessageReservation(message_id=TypeID(new_typeid("msg")))

			def _delta_envelope(
				message_id: TypeID | None,
				delta: AgentDelta,
			) -> dict[str, object]:
				"""build a public sse delta envelope for any streamed message type."""
				nonlocal splice_pending
				envelope: dict[str, object] = {
					"run_id": run_id,
					"agent_id": agent_id,
					"message_id": message_id,
					"delta": strip_private_sdk_metadata(delta.model_dump(mode="json")),
				}
				if message_id is not None and splice_pending:
					envelope["splice"] = streaming_splice_data
					splice_pending = False
				return envelope

			async with contextlib.aclosing(stream):
				async for delta in stream:
					if commit_tracker is not None:
						commit_tracker.raise_if_failed()
					message_id: TypeID | None = None
					completed_reservation: MessageReservation | None = None

					if delta.chat is not None:
						if current_assistant_id is None:
							splice_pending = True
							current_assistant_reservation = _reserve_message()
							current_assistant_id = (
								current_assistant_reservation.message_id
							)
							assistant_accum = SDKAssistantMessage()
						message_id = current_assistant_id
						assistant_accum = assistant_accum.merge(delta.chat.message)

						if delta.chat.done:
							last_completed_assistant_id = current_assistant_id
							if output_writer is not None:
								if current_assistant_reservation is None:
									raise RuntimeError(
										"assistant output has no reservation"
									)
								await _submit_output(
									current_assistant_reservation,
									assistant_accum,
									include_reply_anchor=True,
								)
								completed_reservation = current_assistant_reservation
							current_assistant_id = None
							current_assistant_reservation = None

					if delta.tool is not None:
						delta = delta.model_copy(deep=True)
						assert delta.tool is not None
						splice_pending = True
						tool_reservation = _reserve_message()
						tool_message_id = tool_reservation.message_id
						message_id = tool_message_id
						if delta.tool.metadata is None:
							delta.tool.metadata = {}
						delta.tool.metadata[MESSAGE_ID_KEY] = str(tool_message_id)
						if output_writer is not None:
							await _submit_output(
								tool_reservation,
								delta.tool,
								include_reply_anchor=False,
							)
							completed_reservation = tool_reservation

					if commit_tracker is not None and completed_reservation is not None:
						await commit_tracker.require_committed(
							completed_reservation.message_id
						)
						await commit_tracker.require_processed(
							completed_reservation.message_id
						)
						commit_tracker.raise_if_failed()

					if delta.done:
						message_id = None

					frame = sse_encode(
						event="delta",
						data=_delta_envelope(message_id=message_id, delta=delta),
					)
					await run_streams.publish(run_id, frame)

					if delta.chat is not None and delta.chat.done and message_id:
						streaming_parent_id = message_id
						streaming_splice = streaming_splice.model_copy(
							update={"parent_id": message_id, "replaces": None}
						)
						streaming_splice_data = streaming_splice.model_dump(mode="json")
					if delta.tool is not None and message_id:
						streaming_parent_id = message_id
						streaming_splice = streaming_splice.model_copy(
							update={"parent_id": message_id, "replaces": None}
						)
						streaming_splice_data = streaming_splice.model_dump(mode="json")

			if output_writer is not None:
				if current_assistant_reservation is not None:
					partial_message_id = await _settle_output()
					await safe_rollback(session)
					await terminate_run(
						run_id,
						reason="generation failed",
						partial_message_id=partial_message_id,
					)
					return
				await _finish_output_writer()
			if commit_tracker is not None:
				commit_tracker.raise_if_failed()

		except asyncio.CancelledError:

			async def _cancel_cleanup() -> None:
				"""finalize partial state and broadcasts for a cancelled stream."""
				requested_reason = (
					await run_registry.cancellation_reason(run_id) or "cancelled"
				)
				partial_message_id: TypeID | None = None
				output_failed = False
				try:
					partial_message_id = await _settle_output()
				except BaseException:
					output_failed = True
					logger.exception(
						"failed to settle output for cancelled run",
						extra={"run_id": str(run_id)},
					)
				await safe_rollback(session)
				await terminate_run(
					run_id,
					reason="generation failed" if output_failed else requested_reason,
					partial_message_id=partial_message_id,
				)

			await _await_finalizer(
				_cancel_cleanup(),
				f"run-cancel-finalizer:{run_id}",
			)
			raise
		except SDKGenerationError as exc:
			try:
				partial_message_id = await _settle_output()
			except BaseException:
				await safe_rollback(session)
				await terminate_run(run_id, reason="generation failed")
				return
			logger.warning(
				"sdk generation error during agent streaming",
				extra={
					"reason": exc.reason,
					"provider": exc.provider,
					"status_code": exc.status_code,
					"code": exc.code,
					"retryable": exc.retryable,
				},
				exc_info=True,
			)
			await safe_rollback(session)
			await terminate_run(
				run_id,
				reason=exc.reason,
				partial_message_id=partial_message_id,
			)
			return
		except Exception:
			if commit_tracker is not None:
				try:
					commit_tracker.raise_if_failed()
				except BaseException:
					await safe_rollback(session)
					await terminate_run(run_id, reason="generation failed")
					return
			try:
				partial_message_id = await _settle_output()
			except BaseException:
				await safe_rollback(session)
				await terminate_run(run_id, reason="generation failed")
				return
			logger.exception("error during agent streaming")
			await safe_rollback(session)
			await terminate_run(
				run_id,
				reason="generation failed",
				partial_message_id=partial_message_id,
			)
			return
		finally:
			await _await_finalizer(
				_settle_final_assistant_reference(),
				f"run-message-reference:{run_id}",
			)

		if output_writer is not None:
			assert thread_id is not None  # persist=True requires a thread_id
			if last_completed_assistant_id is not None:
				try:
					async with async_session_local() as task_session:
						await notify_agent_answer(
							thread_id,
							agent_id,
							last_completed_assistant_id,
							task_session,
						)
				except Exception:
					# the answer is already durable; failing to announce it
					# must not turn a finished run into a failed one.
					logger.exception("failed to notify an agent answer")
			try:
				async with async_session_local() as task_session:
					await schedule_post_run_thread_upkeep(
						thread_id,
						task_session,
					)
			except Exception:
				logger.exception("failed to schedule post-run thread upkeep")

		rs_terminated = await run_registry.complete_run(run_id)
		await release_thread_access_cursor(thread_id)
		dropped = list(rs_terminated.in_flight_steering) if rs_terminated else []
		schedule_terminate_broadcast(
			thread_id, agent_id, run_id, error=False, dropped_steering=dropped
		)
