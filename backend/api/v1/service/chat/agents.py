"""agent building and execution logic."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import async_session_local
from api.local_tasks import create_background_task
from api.models.access_rule import AccessLevel
from api.models.agent import Agent as AgentORM
from api.models.event import Event
from api.models.event_types import EventType
from api.models.model import Model
from api.permissions import ResourceType
from api.schemas.message import MessageCreate
from api.schemas.runs import ClientContext, RunInput, ToolChoice
from api.settings import settings as app_settings
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters import ToolResultTruncationFilter, resolve_filters
from api.v1.service.chat.filters.chat_context import ChatContextFilter
from api.v1.service.chat.filters.citation_index import (
	CitationIndexFilter,
	resolve_assistant_citations,
)
from api.v1.service.chat.filters.context_windowing import ContextWindowingFilter
from api.v1.service.chat.filters.file_resolve import FileResolveFilter
from api.v1.service.chat.hooks import resolve_hooks
from api.v1.service.chat.message_metadata import (
	MESSAGE_ID_KEY,
	MODEL_ID_KEY,
	NEXT_CITATION_INDEX_KEY,
)
from api.v1.service.chat.models import build_chat_model
from api.v1.service.chat.run_helpers import (
	broadcast_run_event,
	inject_system_instructions,
	load_sdk_thread,
	message_to_sse_data,
	safe_rollback,
	sse_event,
)
from api.v1.service.chat.run_status import run_status_store
from api.v1.service.chat.steering import (
	broadcast_steering_event,
	persist_steering_state,
	prepare_steering,
)
from api.v1.service.chat.tools.registry import resolve_tools
from api.v1.service.chat.user_message import create_run_user_message, resolve_run_input
from api.v1.service.embeddings import embed_text
from api.v1.service.events import build_live_persisting_event_emitter
from api.v1.tasks.threads import schedule_thread_inactivity_maintenance
from nokodo_ai import Agent as SDKAgent
from nokodo_ai import Filter as SDKFilter
from nokodo_ai import Hook as SDKHook
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.deltas import AgentDelta
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import TextContent
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.tool import Tool
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)


class _PersistStop:
	"""sentinel used to signal the persistence worker to drain and exit."""


_PERSIST_STOP = _PersistStop()

type PersistQueueItem = tuple[TypeID, SDKMessage] | _PersistStop


async def _resolve_run_thread(
	agent: AgentORM,
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID | None,
	initial_parent_id: TypeID | None,
	resolved_input: list,
	client_context: ClientContext | None,
	persist: bool,
) -> tuple[SDKThread, TypeID | None]:
	"""resolve the SDKThread and head id used to seed the agent run.

	unifies the persist and ephemeral paths:

	- persist=True: load the thread from the DB starting at ``initial_parent_id``,
		inject system instructions, return the thread + the resolved head id
		(which becomes ``initial_parent_id`` for downstream message persistence).
	- persist=False with thread_id: load the thread for context only, append
		any ephemeral user input, inject system instructions, return.
	- persist=False without thread_id: synthesize a thread from the resolved
		input alone.

	returns ``(thread, head_id)``. ``head_id`` is non-None only when persisting.
	"""
	if persist:
		assert thread_id is not None  # persist=True requires a thread_id
		sdk_thread, head_id = await load_sdk_thread(
			thread_id,
			session,
			principal=principal,
			parent_id=initial_parent_id,
		)
		resolved_head: TypeID | None = (
			initial_parent_id
			if initial_parent_id is not None
			else (TypeID(str(head_id)) if head_id else None)
		)
		thread = await inject_system_instructions(
			agent,
			sdk_thread,
			session=session,
			principal=principal,
			client_context=client_context,
		)
		return thread, resolved_head

	# ephemeral: no persistence; load thread context if thread_id provided
	if thread_id is not None:
		try:
			sdk_thread, _ = await load_sdk_thread(
				thread_id,
				session,
				principal=principal,
			)
		except HTTPException:
			raise
		except Exception:
			logger.exception(
				"failed to load thread context for ephemeral run",
				extra={"thread_id": str(thread_id)},
			)
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="failed to load thread context",
			)
	else:
		sdk_thread = SDKThread(messages=[])

	if resolved_input:
		sdk_thread = sdk_thread.model_copy(
			update={
				"messages": [
					*sdk_thread.messages,
					SDKUserMessage(content=resolved_input),
				]
			}
		)

	try:
		thread = await inject_system_instructions(
			agent,
			sdk_thread,
			session=session,
			principal=principal,
			client_context=client_context,
		)
	except Exception:
		logger.exception("failed to inject system instructions")
		thread = sdk_thread

	return thread, None


async def _finalize_partial_assistant_on_cancel(
	run_id: TypeID,
	agent_id: TypeID,
	current_assistant_id: TypeID | None,
	chat_deltas: list[SDKAssistantMessage],
	persist: bool,
	message_queue: asyncio.Queue[PersistQueueItem],
) -> None:
	"""persist whatever assistant content streamed before the cancel hit.

	called from the cancel handler so subscribers, the in-memory RunStatus
	messages, and (when persisting) the DB all reflect the partial result
	the user already saw on screen. partial messages are flagged via
	``metadata.partial_reason='cancelled'`` so DB consumers can distinguish
	them from complete ones.
	"""
	if current_assistant_id is None or not chat_deltas:
		return
	partial = SDKAssistantMessage()
	for dm in chat_deltas:
		partial = partial.merge(dm)
	partial_content: list[dict[str, object]] = []
	for part in partial.content or []:
		if isinstance(part, TextContent):
			partial_content.append({"type": "text", "text": part.text})
	partial_tc = (
		[tc.model_dump(mode="json") for tc in partial.tool_calls]
		if partial.tool_calls
		else []
	)
	try:
		await run_status_store.add_message(
			run_id,
			message_id=current_assistant_id,
			message_type="assistant",
			content=partial_content,
			sender_agent_id=agent_id,
			tool_calls=partial_tc,
		)
		if persist:
			partial.metadata = {
				**(partial.metadata or {}),
				"partial": True,
				"partial_reason": "cancelled",
			}
			await message_queue.put((current_assistant_id, partial))
	except Exception:
		logger.exception(
			"failed to finalize partial assistant message on cancel",
			extra={"run_id": run_id, "message_id": current_assistant_id},
		)


def _schedule_terminate_broadcast(
	thread_id: TypeID | None,
	agent_id: TypeID,
	run_id: TypeID,
	error: bool,
	dropped_steering: list[TypeID] | None = None,
) -> None:
	"""fire a run.completed/run.error broadcast for a thread-bound run.

	if ``dropped_steering`` ids are supplied, also fires a
	``run.steering.dropped`` broadcast and persists the metadata flip on
	each affected message.

	no-op for ephemeral runs (no thread to fan out to).
	"""
	if thread_id is None:
		return
	create_background_task(
		broadcast_run_event(
			thread_id=thread_id,
			agent_id=agent_id,
			run_id=run_id,
			started=False,
			error=error,
		),
		name="broadcast_run_error" if error else "broadcast_run_completed",
	)
	if dropped_steering:
		create_background_task(
			_broadcast_dropped_steering(
				thread_id=thread_id,
				agent_id=agent_id,
				run_id=run_id,
				dropped=dropped_steering,
			),
			name="broadcast_steering_dropped",
		)


def _public_delta_payload(value: object) -> object:
	"""return a stream payload copy with every metadata object public-sanitized."""
	if isinstance(value, Mapping):
		payload: dict[str, object] = {}
		for key, item in value.items():
			key_str = str(key)
			if key_str == "metadata" and isinstance(item, Mapping):
				payload[key_str] = {
					str(meta_key): meta_value
					for meta_key, meta_value in item.items()
					if not str(meta_key).startswith("_")
				}
			else:
				payload[key_str] = _public_delta_payload(item)
		return payload
	if isinstance(value, list):
		return [_public_delta_payload(item) for item in value]
	return value


def _content_payload_list(value: object) -> list[dict[str, object]]:
	"""coerce a serialized content field into run-status content parts."""
	if not isinstance(value, list):
		return []
	content: list[dict[str, object]] = []
	for item in value:
		if isinstance(item, Mapping):
			content.append({str(key): item_value for key, item_value in item.items()})
	return content


async def _broadcast_dropped_steering(
	thread_id: TypeID,
	agent_id: TypeID,
	run_id: TypeID,
	dropped: list[TypeID],
) -> None:
	"""broadcast run.steering.dropped and persist the metadata flip."""
	if not dropped:
		return
	await persist_steering_state(dropped, "dropped", only_if_current="queued")
	await broadcast_steering_event(
		event_type=EventType.RUN_STEERING_DROPPED,
		thread_id=thread_id,
		agent_id=agent_id,
		run_id=run_id,
		message_ids=dropped,
	)


async def _load_agent(
	agent_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> AgentORM:
	"""load an agent with auth check + model/provider relationships.

	combines access verification and eager loading into a single query
	using the resource access predicate.
	"""
	stmt = (
		select(AgentORM)
		.options(selectinload(AgentORM.model).selectinload(Model.provider))
		.where(
			AgentORM.id == agent_id,
			resource_access_predicate(
				principal,
				ResourceType.AGENT,
				required_level=AccessLevel.READER,
			),
		)
	)
	result = await session.execute(stmt)
	agent = result.scalars().one_or_none()

	if agent is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="agent not found",
		)

	if agent.model is None:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="agent has no model configured",
		)

	return agent


def build_agent(
	chat_model: ChatModel,
	tools: list[Tool[AppContext]] | None = None,
	filters: list[SDKFilter[AppContext]] | None = None,
	hooks: list[SDKHook[AppContext]] | None = None,
	max_iterations: int = 10,
) -> SDKAgent[AppContext]:
	"""build an sdk Agent with the given configuration.

	args:
		chat_model: configured ChatModel for the agent
		tools: list of tools the agent can use
		filters: list of pre-processing filters
		hooks: list of post-execution hooks
		max_iterations: maximum agentic loop iterations

	returns:
		configured SDKAgent ready for execution
	"""
	return SDKAgent[AppContext](
		chat_model=chat_model,
		tools=tools or [],
		filters=filters or [],
		hooks=hooks or [],
		max_iterations=max_iterations,
	)


async def build_agent_from_orm(
	agent_orm: AgentORM,
	context: AppContext,
) -> SDKAgent[AppContext]:
	"""build an sdk Agent from an orm Agent instance.

	this loads the model, resolves tools, and applies agent configuration.

	args:
		agent_orm: orm Agent with model relationship loaded
		context: execution context for tool and filter execution

	returns:
		configured SDKAgent ready for execution
	"""
	if agent_orm.model is None:
		raise ValueError(f"agent {agent_orm.id} has no model configured")
	cfg = agent_orm.config or {}
	raw_chat_model_config = cfg.get("chat_model")
	if raw_chat_model_config is not None and not isinstance(
		raw_chat_model_config, Mapping
	):
		raise ValueError(f"agent {agent_orm.id} chat_model config must be an object")
	chat_model_config = (
		{str(key): value for key, value in raw_chat_model_config.items()}
		if isinstance(raw_chat_model_config, Mapping)
		else None
	)

	chat_model = build_chat_model(
		agent_orm.model,
		params=chat_model_config,
	)

	# resolve plugins from agent's plugin_ids
	tools = await resolve_tools(
		tool_ids=agent_orm.plugin_ids,
	)
	filters = resolve_filters(agent_orm.plugin_ids)
	filters.insert(0, ToolResultTruncationFilter())
	filters.append(ChatContextFilter())
	filters.append(FileResolveFilter())
	filters.append(CitationIndexFilter())
	filters.append(ContextWindowingFilter())
	hooks = resolve_hooks(agent_orm.plugin_ids)

	# extract max_iterations from agent config
	max_iterations = 10
	if isinstance(cfg.get("max_iterations"), int):
		max_iterations = int(cfg["max_iterations"])

	return build_agent(
		chat_model=chat_model,
		tools=tools,
		filters=filters,
		hooks=hooks,
		max_iterations=max_iterations,
	)


async def run_agent(
	thread_id: TypeID | None,
	agent_id: TypeID,
	principal: Principal,
	input: RunInput | None = None,
	parent_id: TypeID | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	persist: bool = True,
	tool_choice: ToolChoice | None = None,
	run_id_override: TypeID | None = None,
	ready_event: asyncio.Event | None = None,
) -> AsyncIterator[bytes]:
	"""stream a thread run as sse events.

	when ``persist`` is True (default) full DB persistence is applied:
	messages are saved, run status is tracked, and metadata is generated.

	when ``persist`` is False an ephemeral inference is performed:
	no thread, messages, or metadata are written to the database.
	``thread_id`` may be None in this case; ``input`` must be provided.

	when ``run_id_override`` is provided, the caller has already allocated the
	run id (used for background-task execution where the caller needs
	the id before this generator starts publishing).

	when ``ready_event`` is provided, it is set immediately after the run is
	registered in the run_status_store. callers driving this generator as a
	background task can wait on this event before subscribing to the store,
	guaranteeing they will not miss any frames.

	Each SSE ``delta`` event includes:
	- run_id: stable ID for this run
	- message_id: stable ID for the currently streaming message
	- delta: the raw AgentDelta payload (Pydantic JSON)
	"""
	run_id = run_id_override if run_id_override is not None else new_typeid("run")

	async with async_session_local() as session:
		initial_parent_id: TypeID | None = None

		# resolve structured input to content parts
		resolved_input = await resolve_run_input(input, session) if input else []

		# register run in status store + (when on a thread) broadcast
		# run.started. ``persist`` only gates DB writes (messages, metadata);
		# every run lives in the registry so it is cancellable, observable,
		# and resumable regardless of whether we persist its outputs.
		await run_status_store.start_run(
			run_id=run_id,
			agent_id=agent_id,
			user_id=principal.user_id,
			thread_id=thread_id,
		)
		# self-attach the producer task so cancel_run works from the very
		# first microsecond the run is visible. when this generator is
		# being driven by a background task (the normal path), current_task()
		# IS that producer; when it is driven inline by an HTTP request
		# (legacy / tests), there is no producer to cancel and the attach
		# becomes a no-op via cancel_run's task.done() guard.
		current = asyncio.current_task()
		if current is not None:
			await run_status_store.attach_task(run_id, current)
		if ready_event is not None:
			ready_event.set()
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

		if persist and resolved_input:
			assert thread_id is not None  # persist=True requires a thread_id
			user_msg = await create_run_user_message(
				thread_id,
				session,
				principal=principal,
				resolved_input=resolved_input,
				parent_id=parent_id,
				run_id=run_id,
				origin_session_id=origin_session_id,
				attachment_actions=(input.attachment_actions if input else None),
			)
			user_msg_data = message_to_sse_data(user_msg)
			frame = sse_event(event="message_created", data=user_msg_data)
			await run_status_store.publish(run_id, frame)
			yield frame
			initial_parent_id = user_msg.id
			await run_status_store.add_message(
				run_id,
				message_id=user_msg.id,
				message_type="user",
				content=_content_payload_list(user_msg_data.get("content")),
				parent_id=user_msg.parent_id,
				sender_agent_id=None,
				created_at=(
					user_msg.created_at.isoformat() if user_msg.created_at else None
				),
			)
		else:
			initial_parent_id = parent_id

		try:
			agent = await _load_agent(agent_id, session, principal)
		except HTTPException:
			raise
		except Exception:
			logger.exception("failed to load agent")
			err = sse_event(event="error", data={"message": "failed to load agent"})
			done = sse_event(event="done", data={})
			await run_status_store.publish(run_id, err)
			await run_status_store.publish(run_id, done)
			yield err
			yield done
			return

		# background persistence + event correlation state (persist only)
		message_queue: asyncio.Queue[PersistQueueItem] = asyncio.Queue()
		message_persisted: dict[TypeID, asyncio.Event] = {}
		active_message_id_for_events: TypeID | None = None
		persist_parent_override: TypeID | None = None

		# capture model_id for message metadata before the worker starts.
		# this lets downstream consumers (e.g. windowing) know which model
		# produced each assistant message without re-loading the agent.
		_model_id_for_persist: str | None = str(agent.model.id) if agent.model else None

		async def _persist_message_worker(parent_id: TypeID | None) -> None:
			"""persist streamed SDK messages in order for thread-bound runs."""
			nonlocal persist_parent_override
			assert thread_id is not None  # only runs when persist=True
			last_parent_id = parent_id
			while True:
				item = await message_queue.get()
				if isinstance(item, _PersistStop):
					message_queue.task_done()
					return
				message_id, sdk_msg = item
				try:
					async with async_session_local() as bg_session:
						create_in = MessageCreate.from_sdk_message(
							sdk_msg,
							sender_agent_id=agent_id,
						)
						# resolve citations for assistant messages
						if isinstance(sdk_msg, SDKAssistantMessage):
							text = ""
							for part in sdk_msg.content or []:
								if isinstance(part, TextContent) and part.text:
									text += part.text
							citations = resolve_assistant_citations(text, ctx.citations)
							if citations:
								create_in.citations = citations
							# stamp the running index so future runs can
							# pick up without loading the full branch.
							if ctx.citations:
								nci = ctx.citations[-1].index + 1
								create_in.metadata[NEXT_CITATION_INDEX_KEY] = nci
						create_in.metadata["run_id"] = run_id
						if _model_id_for_persist:
							create_in.metadata[MODEL_ID_KEY] = _model_id_for_persist
						if persist_parent_override is not None:
							last_parent_id = persist_parent_override
							persist_parent_override = None
						create_in.parent_id = last_parent_id
						persisted = await thread_service.create_message(
							thread_id=thread_id,
							message_in=create_in,
							session=bg_session,
							principal=principal,
							message_id=message_id,
							origin_session_id=origin_session_id,
						)
						last_parent_id = TypeID(str(persisted.id))
				except Exception:
					logger.exception(
						"failed to persist streamed message",
						extra={"message_id": str(message_id)},
					)
				finally:
					evt = message_persisted.get(message_id)
					if evt is not None:
						evt.set()
					message_queue.task_done()

		async def _before_persist_event(event: Event) -> None:
			"""wait for the active streamed message before persisting its event."""
			msg_id = event.message_id
			if not msg_id:
				return
			evt = message_persisted.get(msg_id)
			if evt is None:
				return
			try:
				await asyncio.wait_for(evt.wait(), timeout=15)
			except TimeoutError:
				logger.warning(
					"event persistence timed out waiting for message; "
					"dropping message_id",
					extra={"event_id": str(event.id), "message_id": msg_id},
				)
				event.message_id = None

		def _message_id_provider() -> str | None:
			"""return the message id currently receiving streamed tool events."""
			if active_message_id_for_events is None:
				return None
			return str(active_message_id_for_events)

		async def _wait_for_persisted_parent(
			message_id: TypeID | None,
		) -> None:
			"""wait for a streamed parent message before attaching steering output."""
			if message_id is None:
				return
			evt = message_persisted.get(message_id)
			if evt is None:
				return
			try:
				await asyncio.wait_for(evt.wait(), timeout=15)
			except TimeoutError:
				logger.warning(
					"timed out waiting for steering parent persistence",
					extra={"message_id": str(message_id)},
				)

		if persist:
			emitter = build_live_persisting_event_emitter(
				message_id_provider=_message_id_provider,
				before_persist=_before_persist_event,
			)
		else:
			# ephemeral run - no thread to persist events to
			async def _noop_emitter(_event: Event) -> None:
				"""ignore tool events for ephemeral runs."""
				pass

			emitter = _noop_emitter

		ctx = AppContext(
			session=session,
			principal=principal,
			run_id=run_id,
			agent_id=agent_id,
			thread_id=thread_id,
			event_emitter=emitter,
			context_window=(agent.model.context_window if agent.model else None),
		)

		try:
			sdk_agent = await build_agent_from_orm(agent, ctx)
		except Exception:
			logger.exception("failed to build agent")
			err = sse_event(
				event="error", data={"message": "failed to initialize agent"}
			)
			done = sse_event(event="done", data={})
			await run_status_store.publish(run_id, err)
			await run_status_store.publish(run_id, done)
			yield err
			yield done
			return

		if persist:
			assert thread_id is not None  # persist=True requires a thread_id
		thread, resolved_head = await _resolve_run_thread(
			agent,
			session,
			principal,
			thread_id=thread_id,
			initial_parent_id=initial_parent_id,
			resolved_input=resolved_input,
			client_context=client_context,
			persist=persist,
		)
		if persist and resolved_head is not None:
			initial_parent_id = resolved_head

		# build retrieval context explicitly before the agent/filter loop.
		# filters read from ctx.retrieval rather than computing their own.
		# when retrieval_pre_build is False, each filter builds its own query.
		if app_settings.ai.retrieval_pre_build:
			_turns = thread.recent_turns(app_settings.ai.retrieval_turns)
			if _turns:
				ctx.retrieval.query_text = "\n".join(_turns)
				ctx.retrieval.query_embedding = await embed_text(
					text=ctx.retrieval.query_text, session=session
				)

		streaming_parent_id: TypeID | None = initial_parent_id

		def _advance_parent_after_steering(message_id: TypeID) -> None:
			"""advance streaming and persistence parents after steering injection."""
			nonlocal persist_parent_override, streaming_parent_id
			streaming_parent_id = message_id
			persist_parent_override = message_id

		worker_task: asyncio.Task[object] | None = None
		steering_subscriber: asyncio.Task[None] | None = None
		try:
			if persist:
				worker_task = create_background_task(
					_persist_message_worker(parent_id=initial_parent_id),
					name="message_persist_worker",
				)

			run_agent_instance, steering_subscriber = await prepare_steering(
				run_id=run_id,
				sdk_agent=sdk_agent,
				agent_config=agent.parsed_config,
				thread_id=thread_id,
				agent_id=agent_id,
				parent_id_provider=lambda: streaming_parent_id,
				wait_for_parent_persisted=_wait_for_persisted_parent,
				on_parent_advanced=_advance_parent_after_steering,
			)

			def _alloc_message_id() -> TypeID:
				"""allocate a deterministic message id and persistence wait handle."""
				message_id = TypeID(new_typeid("msg"))
				message_persisted[message_id] = asyncio.Event()
				return message_id

			def _delta_envelope(
				message_id: TypeID | None,
				delta: AgentDelta,
			) -> dict[str, object]:
				"""build a public sse delta envelope for any streamed message type."""
				return {
					"run_id": run_id,
					"agent_id": agent_id,
					"message_id": message_id,
					"parent_id": streaming_parent_id,
					"delta": _public_delta_payload(delta.model_dump(mode="json")),
				}

			current_assistant_id: TypeID | None = None
			# deferred merge: collect deltas, merge once on completion
			_chat_deltas: list[SDKAssistantMessage] = []
			# incremental tracking for run status (avoids per-token merge)
			_streaming_text = ""
			_streaming_tc: list[dict[str, object]] = []

			# outer loop: re-invoke the agent if steering arrived after the
			# last filter pass. the SDK's SteeringFilter only runs between
			# agent iterations; if a user steers during the final iteration
			# (or while the agent is producing its terminal message), the
			# inbox would otherwise be dropped on natural completion. by
			# kicking off another agent.run() we let the filter drain the
			# queue and the agent respond to the queued user message(s).
			steering_continuation_count = 0
			max_steering_continuations = 8
			while True:
				stream = await run_agent_instance.run(
					thread,
					app_context=ctx,
					tool_choice=tool_choice or "auto",
					stream=True,
				)

				async for delta in stream:
					message_id: TypeID | None = None

					if delta.chat is not None:
						if current_assistant_id is None:
							current_assistant_id = _alloc_message_id()
							_chat_deltas = []
							_streaming_text = ""
							_streaming_tc = []
						message_id = current_assistant_id
						_chat_deltas.append(delta.chat.message)

						if persist:
							# incremental text accumulation
							delta_text = delta.chat.message.text
							if delta_text:
								_streaming_text += delta_text

							# incremental tool call accumulation
							tc_update: list[dict[str, object]] | None = None
							if delta.chat.message.tool_calls:
								for tc in delta.chat.message.tool_calls:
									existing = next(
										(
											t
											for t in _streaming_tc
											if t.get("id") == tc.id
										),
										None,
									)
									if existing is not None:
										if (
											isinstance(tc.arguments, str)
											and tc.arguments
										):
											existing["arguments"] = (
												str(existing.get("arguments", ""))
												+ tc.arguments
											)
										if tc.name:
											existing["name"] = tc.name
									else:
										_streaming_tc.append(
											{
												"id": tc.id,
												"name": tc.name,
												"arguments": (
													tc.arguments
													if isinstance(tc.arguments, str)
													else ""
												),
											}
										)
								tc_update = _streaming_tc

							await run_status_store.update_streaming(
								run_id,
								message_id=current_assistant_id,
								content=_streaming_text,
								tool_calls=tc_update,
							)

						if delta.chat.done:
							# deferred merge - build full message only on completion
							assistant_accum = SDKAssistantMessage()
							for dm in _chat_deltas:
								assistant_accum = assistant_accum.merge(dm)
							content_parts: list[dict[str, object]] = []
							for part in assistant_accum.content or []:
								if isinstance(part, TextContent):
									content_parts.append(
										{"type": "text", "text": part.text}
									)
							tc_data = (
								[
									tc.model_dump(mode="json")
									for tc in assistant_accum.tool_calls
								]
								if assistant_accum.tool_calls
								else []
							)
							await run_status_store.add_message(
								run_id,
								message_id=current_assistant_id,
								message_type="assistant",
								content=content_parts,
								sender_agent_id=agent_id,
								tool_calls=tc_data,
							)
							if persist:
								active_message_id_for_events = current_assistant_id
								await message_queue.put(
									(current_assistant_id, assistant_accum)
								)
							current_assistant_id = None

					if delta.tool is not None:
						tool_message_id = _alloc_message_id()
						message_id = tool_message_id
						if delta.tool.metadata is None:
							delta.tool.metadata = {}
						delta.tool.metadata[MESSAGE_ID_KEY] = str(tool_message_id)
						output = delta.tool.tool_output or ""
						tool_content: list[dict[str, object]] = [
							{"type": "text", "text": output}
						]
						for att in delta.tool.attachments:
							tool_content.append(att.model_dump(mode="json"))
						await run_status_store.add_message(
							run_id,
							message_id=tool_message_id,
							message_type="tool",
							content=tool_content,
						)
						if persist:
							await message_queue.put((tool_message_id, delta.tool))

					if delta.done:
						message_id = None

					frame = sse_event(
						event="delta",
						data=_delta_envelope(message_id=message_id, delta=delta),
					)
					await run_status_store.publish(run_id, frame)
					yield frame

					if delta.chat is not None and delta.chat.done and message_id:
						streaming_parent_id = message_id
					if delta.tool is not None and message_id:
						streaming_parent_id = message_id

				# the SDK agent loop terminated naturally. if steering arrived
				# in the meantime (during the final iteration or after the
				# last filter pass), the SteeringFilter never got a chance to
				# drain the inbox. re-invoke agent.run so the filter runs and
				# the agent processes the queued user message(s).
				if not await run_status_store.has_in_flight_steering(run_id):
					break
				if steering_continuation_count >= max_steering_continuations:
					logger.warning(
						"max steering continuations reached for run %s,"
						" dropping leftover steering",
						run_id,
					)
					break
				steering_continuation_count += 1
				# reset per-stream accumulator state for the next agent.run() pass.
				current_assistant_id = None
				_chat_deltas = []
				_streaming_text = ""
				_streaming_tc = []

		except (GeneratorExit, asyncio.CancelledError):
			# explicit cancellation (cancel_run endpoint, task.cancel(), or
			# producer driver torn down). this is the only path where the run
			# does NOT complete naturally - finalize whatever assistant content
			# we have so far so subscribers, RunStatus.messages, and the DB all
			# reflect the partial result the user already saw streaming.
			#
			# shield the cleanup so a second cancel (re-entrant
			# task.cancel(), shutdown signal) cannot interrupt it midway and
			# leave the run pinned in the store with subscribers waiting on
			# a sentinel that never arrives.
			async def _cancel_cleanup() -> None:
				"""finalize partial state and broadcasts for a cancelled stream."""
				await _finalize_partial_assistant_on_cancel(
					run_id=run_id,
					agent_id=agent_id,
					current_assistant_id=current_assistant_id,
					chat_deltas=_chat_deltas,
					persist=persist,
					message_queue=message_queue,
				)
				await safe_rollback(session)
				rs_terminated = await run_status_store.fail_run(
					run_id, reason="cancelled"
				)
				dropped = rs_terminated.in_flight_steering() if rs_terminated else []
				_schedule_terminate_broadcast(
					thread_id, agent_id, run_id, error=True, dropped_steering=dropped
				)

			await asyncio.shield(_cancel_cleanup())
			raise
		except Exception:
			logger.exception("error during agent streaming")
			await safe_rollback(session)
			rs_terminated = await run_status_store.fail_run(
				run_id, reason="generation failed"
			)
			dropped = rs_terminated.in_flight_steering() if rs_terminated else []
			_schedule_terminate_broadcast(
				thread_id, agent_id, run_id, error=True, dropped_steering=dropped
			)
			yield sse_event(event="error", data={"message": "generation failed"})
			yield sse_event(event="done", data={})
			return
		finally:
			if persist and worker_task is not None and not worker_task.done():
				await message_queue.put(_PERSIST_STOP)
			if steering_subscriber is not None and not steering_subscriber.done():
				steering_subscriber.cancel()

		if persist:
			assert thread_id is not None  # persist=True requires a thread_id
			if worker_task is not None:
				try:
					await asyncio.wait_for(asyncio.shield(worker_task), timeout=30)
				except (TimeoutError, Exception):
					logger.warning(
						"persist worker did not finish cleanly before metadata gen"
					)
			try:
				async with async_session_local() as task_session:
					await schedule_thread_inactivity_maintenance(
						thread_id,
						task_session,
					)
			except Exception:
				logger.exception("failed to schedule thread inactivity maintenance")

		rs_terminated = await run_status_store.complete_run(run_id)
		dropped = rs_terminated.in_flight_steering() if rs_terminated else []
		_schedule_terminate_broadcast(
			thread_id, agent_id, run_id, error=False, dropped_steering=dropped
		)

		yield sse_event(event="done", data={})
