"""agent building and execution logic."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import AsyncSessionLocal
from api.models.access_rule import AccessLevel
from api.models.agent import Agent as AgentORM
from api.models.event import Event
from api.models.message import Message as MessageORM
from api.models.model import Model
from api.permissions import ResourceType
from api.schemas.message import MessageCreate
from api.schemas.runs import ClientContext
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_resource_access
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters import resolve_filters
from api.v1.service.chat.hooks import resolve_hooks
from api.v1.service.chat.models import build_chat_model
from api.v1.service.chat.tools import resolve_tools
from api.v1.service.events import build_event_emitter
from api.v1.service.prompt_runtime import render_agent_instructions
from nokodo_ai import Agent as SDKAgent
from nokodo_ai import Filter as SDKFilter
from nokodo_ai import Hook as SDKHook
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.deltas import AgentDelta
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
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
		context=context,
	)
	filters = resolve_filters(agent_orm.plugin_ids)
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


def _sse_event(*, event: str, data: dict[str, object]) -> bytes:
	"""format an sse event."""
	payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
	return f"event: {event}\ndata: {payload}\n\n".encode()


def _message_to_sse_data(msg: MessageORM) -> dict[str, object]:
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


async def run_agent(
	thread_id: TypeID,
	agent_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	input: str | None = None,
	parent_id: TypeID | None = None,
	client_context: ClientContext | None = None,
) -> AsyncIterator[bytes]:
	"""stream a thread run as sse events.

	This is a faithful transport of SDK AgentDelta objects. Each SSE `delta`
	event includes:
	- run_id: stable ID for this run
	- message_id: stable ID for the currently streaming message (generated on the
		first chunk of that message and repeated on every chunk)
	- delta: the raw AgentDelta payload (Pydantic JSON)

	Persistence is handled asynchronously in the background so deltas are never
	blocked on the database.
	"""
	run_id = new_typeid("run")

	# authorize: principal must have READER+ on the agent
	await require_resource_access(
		str(agent_id),
		session,
		principal,
		ResourceType.AGENT,
		required_level=AccessLevel.READER,
	)

	if input is not None and input.strip():
		user_msg = await thread_service.create_message(
			thread_id,
			MessageCreate(
				content=input,
				metadata_={"run_id": run_id},
				parent_id=parent_id,
			),
			session,
			principal=principal,
		)
		yield _sse_event(event="message_created", data=_message_to_sse_data(user_msg))
		initial_parent_id: TypeID | None = TypeID(str(user_msg.id))
	else:
		initial_parent_id = parent_id

	try:
		agent = await _load_agent(agent_id, session)
	except HTTPException:
		raise
	except Exception:
		logger.exception("failed to load agent")
		yield _sse_event(event="error", data={"message": "failed to load agent"})
		yield _sse_event(event="done", data={})
		return

	# --- background persistence + event correlation state ---
	message_queue: asyncio.Queue[tuple[str, SDKMessage]] = asyncio.Queue()
	message_persisted: dict[str, asyncio.Event] = {}
	active_message_id_for_events: str | None = None

	def _track_task(name: str, task: asyncio.Task[object]) -> None:
		"""Ensure exceptions from background tasks are visible in logs."""

		def _log_result(done: asyncio.Task[object]) -> None:
			try:
				done.result()
			except Exception:
				logger.exception("background task failed: %s", name)

		task.add_done_callback(_log_result)

	async def _persist_message_worker(*, parent_id: TypeID | None) -> None:
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
					create_in.parent_id = last_parent_id
					persisted = await thread_service.create_message(
						thread_id=thread_id,
						message_in=create_in,
						session=bg_session,
						principal=principal,
						message_id=TypeID(message_id_str),
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
				"event persistence timed out waiting for message; dropping message_id",
				extra={"event_id": str(event.id), "message_id": msg_id},
			)
			event.message_id = None

	def _message_id_provider() -> str | None:
		return active_message_id_for_events

	emitter = build_event_emitter(
		message_id_provider=_message_id_provider,
		before_persist=_before_persist_event,
	)

	# create context with non-blocking emitter
	ctx = AppContext(
		session=session,
		principal=principal,
		agent_id=agent_id,
		thread_id=thread_id,
		event_emitter=emitter,
	)
	try:
		sdk_agent = await build_agent_from_orm(agent, ctx)
	except Exception:
		logger.exception("failed to build agent")
		yield _sse_event(event="error", data={"message": "failed to initialize agent"})
		yield _sse_event(event="done", data={})
		return

	thread_orm = await thread_service.get_thread(
		thread_id,
		session,
		principal=principal,
	)
	# if there was no input, start the persistence chain from the current leaf
	if initial_parent_id is None:
		initial_parent_id = (
			TypeID(str(thread_orm.current_message_id))
			if thread_orm.current_message_id
			else None
		)

	# Ensure we build context from the correct branch point.
	# When regenerating/branching, we must limit history to the parent_id.
	original_head = thread_orm.current_message_id
	if initial_parent_id and original_head != initial_parent_id:
		thread_orm.current_message_id = initial_parent_id

	try:
		branch_orm = await thread_service.get_current_branch(
			thread_id,
			session,
			principal=principal,
			include_hidden=False,
		)
		sdk_thread = SDKThread(
			created_at=thread_orm.created_at,
			messages=[m.to_sdk() for m in branch_orm],
			metadata=thread_orm.metadata_,
		)
		thread = await inject_system_instructions(
			agent,
			sdk_thread,
			session=session,
			principal=principal,
			client_context=client_context,
		)
	finally:
		# Restore original head to avoid unintended side effects on the session object
		if initial_parent_id and original_head != initial_parent_id:
			thread_orm.current_message_id = original_head

	worker_task: asyncio.Task[object] | None = None
	try:
		# start message persistence worker
		worker_task = asyncio.create_task(
			_persist_message_worker(parent_id=initial_parent_id)
		)

		stream = await sdk_agent.run(
			thread,
			app_context=ctx,
			tool_choice="auto",
			stream=True,
		)

		def _alloc_message_id() -> str:
			message_id_str = str(TypeID(new_typeid("msg")))
			message_persisted[message_id_str] = asyncio.Event()
			return message_id_str

		def _delta_envelope(
			*,
			message_id: str | None,
			delta: AgentDelta,
		) -> dict[str, object]:
			return {
				"run_id": str(run_id),
				"message_id": message_id,
				"delta": delta.model_dump(mode="json"),
			}

		current_assistant_id: str | None = None
		assistant_accum = SDKAssistantMessage()

		async for delta in stream:
			message_id: str | None = None
			# assistant streaming chunks
			if delta.chat is not None:
				if current_assistant_id is None:
					current_assistant_id = _alloc_message_id()
					assistant_accum = SDKAssistantMessage()
				message_id = current_assistant_id
				assistant_accum = assistant_accum.merge(delta.chat.message)
				# mark which message tool events should correlate to
				if delta.chat.done:
					active_message_id_for_events = current_assistant_id
					await message_queue.put((current_assistant_id, assistant_accum))
					current_assistant_id = None

			# tool results (single message)
			if delta.tool is not None:
				tool_message_id = _alloc_message_id()
				message_id = tool_message_id
				await message_queue.put((tool_message_id, delta.tool))

			# agent run completion sentinel has no message_id
			if delta.done:
				message_id = None

			yield _sse_event(
				event="delta",
				data=_delta_envelope(message_id=message_id, delta=delta),
			)

	except Exception:
		logger.exception("error during agent streaming")
		yield _sse_event(event="error", data={"message": "generation failed"})
		yield _sse_event(event="done", data={})
		return
	finally:
		# stop worker and let it drain queued persistence in the background
		if worker_task is not None and not worker_task.done():
			await message_queue.put(("__STOP__", SDKAssistantMessage()))
			_track_task("message_persist_worker", worker_task)

	yield _sse_event(event="done", data={})

	# once the run is complete, opportunistically generate thread metadata.
	# this is non-blocking and only applies after the first user→assistant turn.
	try:
		model = agent.model
		if model is None:
			raise RuntimeError("agent has no model configured")
		chat_model = build_chat_model(model)

		# temporary: run inline until taskiq exists
		async def _generate() -> None:
			from api.core.database import AsyncSessionLocal

			async with AsyncSessionLocal() as session:
				await thread_service.generate_thread_metadata(
					session,
					thread_id=thread_id,
					chat_model=chat_model,
				)

		asyncio.create_task(_generate())
	except Exception:
		logger.exception(
			"failed to enqueue thread metadata generation",
			extra={"thread_id": str(thread_id)},
		)
