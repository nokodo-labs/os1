"""agent building and execution logic."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import AsyncSessionLocal
from api.models.access_rule import AccessLevel
from api.models.agent import Agent as AgentORM
from api.models.event import Event
from api.models.model import Model
from api.permissions import ResourceType
from api.schemas.message import MessageCreate
from api.schemas.runs import ClientContext, RunInput, ToolChoice
from api.tasks import create_background_task
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_resource_access
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters import ToolResultTruncationFilter, resolve_filters
from api.v1.service.chat.filters.context_windowing import ContextWindowingFilter
from api.v1.service.chat.filters.file_resolve import FileResolveFilter
from api.v1.service.chat.hooks import resolve_hooks
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
from api.v1.service.chat.tools import resolve_tools
from api.v1.service.chat.user_message import create_run_user_message, resolve_run_input
from api.v1.service.events import build_event_emitter
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


async def _load_agent(agent_id: TypeID, session: AsyncSession) -> AgentORM:
	"""load an agent with its model + provider relationships."""
	stmt = (
		select(AgentORM)
		.options(selectinload(AgentORM.model).selectinload(Model.provider))
		.where(AgentORM.id == agent_id)
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
	*,
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
	*,
	temperature: float | None = None,
	max_tokens: int | None = None,
) -> SDKAgent[AppContext]:
	"""build an sdk Agent from an orm Agent instance.

	this loads the model, resolves tools, and applies agent configuration.

	args:
		agent_orm: orm Agent with model relationship loaded
		temperature: optional temperature override
		max_tokens: optional max_tokens override
		context: execution context for tool and filter execution

	returns:
		configured SDKAgent ready for execution
	"""
	if agent_orm.model is None:
		raise ValueError(f"agent {agent_orm.id} has no model configured")

	chat_model = build_chat_model(
		agent_orm.model,
		temperature=temperature,
		max_tokens=max_tokens,
	)

	# resolve plugins from agent's plugin_ids
	tools = await resolve_tools(
		tool_ids=agent_orm.plugin_ids,
	)
	filters = resolve_filters(agent_orm.plugin_ids)
	filters.insert(0, ToolResultTruncationFilter())
	filters.append(FileResolveFilter())
	filters.append(ContextWindowingFilter())
	hooks = resolve_hooks(agent_orm.plugin_ids)

	# extract max_iterations from agent config
	max_iterations = 10
	cfg = agent_orm.config or {}
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
	*,
	input: RunInput | None = None,
	parent_id: TypeID | None = None,
	client_context: ClientContext | None = None,
	origin_session_id: str | None = None,
	persist: bool = True,
	tool_choice: ToolChoice | None = None,
) -> AsyncIterator[bytes]:
	"""stream a thread run as sse events.

	when ``persist`` is True (default) full DB persistence is applied:
	messages are saved, run status is tracked, and metadata is generated.

	when ``persist`` is False an ephemeral inference is performed:
	no thread, messages, or metadata are written to the database.
	``thread_id`` may be None in this case; ``input`` must be provided.

	Each SSE ``delta`` event includes:
	- run_id: stable ID for this run
	- message_id: stable ID for the currently streaming message
	- delta: the raw AgentDelta payload (Pydantic JSON)
	"""
	run_id = new_typeid("run")
	run_id_str = str(run_id)

	async with AsyncSessionLocal() as session:
		# authorize: principal must have READER+ on the agent
		await require_resource_access(
			str(agent_id),
			session,
			principal,
			ResourceType.AGENT,
			required_level=AccessLevel.READER,
		)

		initial_parent_id: TypeID | None = None

		# resolve structured input to content parts
		resolved_input = await resolve_run_input(input, session) if input else []

		if persist:
			assert thread_id is not None  # persist=True requires a thread_id
			# register run in status store + broadcast run.started
			await run_status_store.start_run(
				run_id=run_id_str,
				thread_id=str(thread_id),
				agent_id=str(agent_id),
				user_id=principal.user_id,
			)
			create_background_task(
				broadcast_run_event(
					thread_id=str(thread_id),
					agent_id=str(agent_id),
					run_id=run_id_str,
					started=True,
				),
				name="broadcast_run_started",
			)
			if resolved_input:
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
				await run_status_store.publish(run_id_str, frame)
				yield frame
				initial_parent_id = TypeID(str(user_msg.id))
				user_content = user_msg_data.get("content")
				await run_status_store.add_message(
					run_id_str,
					message_id=str(user_msg.id),
					message_type="user",
					content=user_content if isinstance(user_content, list) else [],
					parent_id=str(user_msg.parent_id) if user_msg.parent_id else None,
					sender_agent_id=None,
					created_at=(
						user_msg.created_at.isoformat() if user_msg.created_at else None
					),
				)
			else:
				initial_parent_id = parent_id

		try:
			agent = await _load_agent(agent_id, session)
		except HTTPException:
			raise
		except Exception:
			logger.exception("failed to load agent")
			err = sse_event(event="error", data={"message": "failed to load agent"})
			done = sse_event(event="done", data={})
			if persist:
				await run_status_store.publish(run_id_str, err)
				await run_status_store.publish(run_id_str, done)
			yield err
			yield done
			return

		# --- background persistence + event correlation state (persist only) ---
		message_queue: asyncio.Queue[tuple[str, SDKMessage]] = asyncio.Queue()
		message_persisted: dict[str, asyncio.Event] = {}
		active_message_id_for_events: str | None = None

		# capture model_id for message metadata before the worker starts.
		# this lets downstream consumers (e.g. windowing) know which model
		# produced each assistant message without re-loading the agent.
		_model_id_for_persist: str | None = str(agent.model.id) if agent.model else None

		async def _persist_message_worker(*, parent_id: TypeID | None) -> None:
			assert thread_id is not None  # only runs when persist=True
			last_parent_id = parent_id
			while True:
				item = await message_queue.get()
				if item[0] == "__STOP__":
					message_queue.task_done()
					return
				message_id_str, sdk_msg = item
				try:
					async with AsyncSessionLocal() as bg_session:
						create_in = MessageCreate.from_sdk_message(
							sdk_msg,
							sender_agent_id=agent_id,
						)
						create_in.metadata["run_id"] = run_id
						if _model_id_for_persist:
							create_in.metadata["model_id"] = _model_id_for_persist
						create_in.parent_id = last_parent_id
						persisted = await thread_service.create_message(
							thread_id=thread_id,
							message_in=create_in,
							session=bg_session,
							principal=principal,
							message_id=TypeID(message_id_str),
							origin_session_id=origin_session_id,
						)
						last_parent_id = TypeID(str(persisted.id))
				except Exception:
					logger.exception(
						"failed to persist streamed message",
						extra={"message_id": message_id_str},
					)
				finally:
					evt = message_persisted.get(message_id_str)
					if evt is not None:
						evt.set()
					message_queue.task_done()

		async def _before_persist_event(event: Event) -> None:
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
			return active_message_id_for_events

		_has_user_message = persist and bool(resolved_input)
		if _has_user_message:
			emitter = build_event_emitter(
				message_id_provider=_message_id_provider,
				before_persist=_before_persist_event,
			)
		else:
			# no user message (regeneration / ephemeral) - suppress attachment
			# lifecycle events. decay/reveal still work via message history,
			# but events are not persisted since there is no message to scope
			# them to.
			async def _noop_emitter(_event: Event) -> None:
				pass

			emitter = _noop_emitter

		ctx = AppContext(
			session=session,
			principal=principal,
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
			if persist:
				await run_status_store.publish(run_id_str, err)
				await run_status_store.publish(run_id_str, done)
			yield err
			yield done
			return

		if persist:
			assert thread_id is not None  # persist=True requires a thread_id
			sdk_thread, head_id = await load_sdk_thread(
				thread_id,
				session,
				principal=principal,
				parent_id=initial_parent_id,
			)
			if initial_parent_id is None:
				initial_parent_id = TypeID(str(head_id)) if head_id else None
			thread = await inject_system_instructions(
				agent,
				sdk_thread,
				session=session,
				principal=principal,
				client_context=client_context,
			)
		else:
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

		worker_task: asyncio.Task[object] | None = None
		try:
			if persist:
				worker_task = create_background_task(
					_persist_message_worker(parent_id=initial_parent_id),
					name="message_persist_worker",
				)

			stream = await sdk_agent.run(
				thread,
				app_context=ctx,
				tool_choice=tool_choice or "auto",
				stream=True,
			)

			def _alloc_message_id() -> str:
				message_id_str = str(TypeID(new_typeid("msg")))
				message_persisted[message_id_str] = asyncio.Event()
				return message_id_str

			streaming_parent_id: str | None = (
				str(initial_parent_id) if initial_parent_id else None
			)

			def _delta_envelope(
				*,
				message_id: str | None,
				delta: AgentDelta,
			) -> dict[str, object]:
				return {
					"run_id": str(run_id),
					"message_id": message_id,
					"parent_id": streaming_parent_id,
					"delta": delta.model_dump(mode="json"),
				}

			current_assistant_id: str | None = None
			# deferred merge: collect deltas, merge once on completion
			_chat_deltas: list[SDKAssistantMessage] = []
			# incremental tracking for run status (avoids per-token merge)
			_streaming_text = ""
			_streaming_tc: list[dict[str, object]] = []

			async for delta in stream:
				message_id: str | None = None

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
									(t for t in _streaming_tc if t.get("id") == tc.id),
									None,
								)
								if existing is not None:
									if isinstance(tc.arguments, str) and tc.arguments:
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
							run_id_str,
							message_id=current_assistant_id,
							content=_streaming_text,
							tool_calls=tc_update,
						)

					if delta.chat.done:
						if persist:
							# deferred merge - build full message only on completion
							assistant_accum = SDKAssistantMessage()
							for dm in _chat_deltas:
								assistant_accum = assistant_accum.merge(dm)
							active_message_id_for_events = current_assistant_id
							await message_queue.put(
								(current_assistant_id, assistant_accum)
							)
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
								run_id_str,
								message_id=current_assistant_id,
								message_type="assistant",
								content=content_parts,
								sender_agent_id=str(agent_id),
								tool_calls=tc_data,
							)
						current_assistant_id = None

				if delta.tool is not None:
					tool_message_id = (
						_alloc_message_id() if persist else str(new_typeid("msg"))
					)
					message_id = tool_message_id
					if persist:
						await message_queue.put((tool_message_id, delta.tool))
						tool_content: list[dict[str, object]] = []
						if hasattr(delta.tool, "tool_output"):
							output = delta.tool.tool_output or ""
							tool_content = [{"type": "text", "text": output}]
						await run_status_store.add_message(
							run_id_str,
							message_id=tool_message_id,
							message_type="tool",
							content=tool_content,
						)

				if delta.done:
					message_id = None

				frame = sse_event(
					event="delta",
					data=_delta_envelope(message_id=message_id, delta=delta),
				)
				if persist:
					await run_status_store.publish(run_id_str, frame)
				yield frame

				if delta.chat is not None and delta.chat.done and message_id:
					streaming_parent_id = message_id
				if delta.tool is not None and message_id:
					streaming_parent_id = message_id

		except GeneratorExit:
			await safe_rollback(session)
			if persist:
				await run_status_store.fail_run(run_id_str)
				create_background_task(
					broadcast_run_event(
						thread_id=str(thread_id),
						agent_id=str(agent_id),
						run_id=run_id_str,
						started=False,
					),
					name="broadcast_run_completed",
				)
			return
		except Exception:
			logger.exception("error during agent streaming")
			await safe_rollback(session)
			if persist:
				await run_status_store.fail_run(run_id_str)
				create_background_task(
					broadcast_run_event(
						thread_id=str(thread_id),
						agent_id=str(agent_id),
						run_id=run_id_str,
						started=False,
					),
					name="broadcast_run_completed",
				)
			yield sse_event(event="error", data={"message": "generation failed"})
			yield sse_event(event="done", data={})
			return
		finally:
			if persist and worker_task is not None and not worker_task.done():
				await message_queue.put(("__STOP__", SDKAssistantMessage()))

		if persist:
			await run_status_store.complete_run(run_id_str)
			create_background_task(
				broadcast_run_event(
					thread_id=str(thread_id),
					agent_id=str(agent_id),
					run_id=run_id_str,
					started=False,
				),
				name="broadcast_run_completed",
			)

		yield sse_event(event="done", data={})

	if persist:
		assert thread_id is not None  # persist=True requires a thread_id
		create_background_task(
			thread_service.generate_thread_metadata(
				thread_id=thread_id,
				principal=principal,
			),
			name="generate_thread_metadata",
		)
