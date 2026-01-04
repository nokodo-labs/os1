"""agent building and execution logic."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.agent import Agent as AgentORM
from api.models.message import Message as MessageORM
from api.models.model import Model
from api.schemas.message import MessageCreate
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.converters import sdk_message_to_orm_create
from api.v1.service.chat.filters import resolve_filters
from api.v1.service.chat.hooks import resolve_hooks
from api.v1.service.chat.models import build_chat_model
from api.v1.service.chat.tools import resolve_tools
from api.v1.service.prompt_runtime import render_inline_with_prompts
from nokodo_ai import Agent as SDKAgent
from nokodo_ai import Filter as SDKFilter
from nokodo_ai import Hook as SDKHook
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.deltas import AgentDelta
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.thread import Thread as SDKThread
from nokodo_ai.tool import Tool
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass
class RunResult:
	"""result of a thread run."""

	user_message: MessageORM | None
	"""the persisted user input message, if any."""

	produced_messages: list[MessageORM]
	"""all messages produced by the agent during this run."""


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
) -> SDKThread:
	"""inject an agent's rendered system instructions at the start of a thread."""
	if not agent_orm.system_prompt:
		return thread

	rendered = await render_inline_with_prompts(
		session,
		text=agent_orm.system_prompt,
		variables=None,
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
		"sender_agent_id": str(msg.sender_agent_id) if msg.sender_agent_id else None,
		"sender_user_id": str(msg.sender_user_id) if msg.sender_user_id else None,
		"created_at": msg.created_at.isoformat() if msg.created_at else None,
	}


async def run_thread(
	thread_id: TypeID,
	agent_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	input: str | None = None,
) -> RunResult:
	"""run a thread with an agent and persist all produced messages."""
	user_message: MessageORM | None = None
	if input is not None and input.strip():
		user_message = await thread_service.create_message(
			thread_id,
			MessageCreate(content=input),
			session,
			principal=principal,
		)

	agent = await _load_agent(agent_id, session)
	ctx = AppContext(session=session, principal=principal, agent_id=agent_id)
	sdk_agent = await build_agent_from_orm(agent, ctx)

	thread_orm = await thread_service.get_thread(
		thread_id,
		session,
		principal=principal,
	)
	thread = await inject_system_instructions(
		agent,
		thread_orm.to_sdk(),
		session=session,
	)

	produced_sdk = await sdk_agent.run(thread, app_context=ctx, tool_choice="auto")

	produced_messages: list[MessageORM] = []
	for sdk_msg in produced_sdk:
		create_in = sdk_message_to_orm_create(sdk_msg, sender_agent_id=agent_id)
		persisted = await thread_service.create_message(
			thread_id,
			create_in,
			session,
			principal=principal,
		)
		produced_messages.append(persisted)

	return RunResult(user_message=user_message, produced_messages=produced_messages)


async def run_thread_stream(
	thread_id: TypeID,
	agent_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	input: str | None = None,
) -> AsyncIterator[bytes]:
	"""stream a thread run as sse events."""
	if input is not None and input.strip():
		user_msg = await thread_service.create_message(
			thread_id,
			MessageCreate(content=input),
			session,
			principal=principal,
		)
		yield _sse_event(event="message_created", data=_message_to_sse_data(user_msg))

	try:
		agent = await _load_agent(agent_id, session)
	except HTTPException:
		raise
	except Exception:
		logger.exception("failed to load agent")
		yield _sse_event(event="error", data={"message": "failed to load agent"})
		yield _sse_event(event="done", data={})
		return

	ctx = AppContext(session=session, principal=principal, agent_id=agent_id)
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
	thread = await inject_system_instructions(
		agent,
		thread_orm.to_sdk(),
		session=session,
	)

	try:
		start_len = len(thread.messages)
		stream = await sdk_agent.run(
			thread,
			app_context=ctx,
			tool_choice="auto",
			stream=True,
		)

		async for delta in stream:
			if delta.chat is not None and delta.chat.message.text:
				yield _sse_event(
					event="text_delta",
					data={"text": delta.chat.message.text},
				)

		produced = thread.messages[start_len:]
		for sdk_msg in produced:
			create_in = sdk_message_to_orm_create(sdk_msg, sender_agent_id=agent_id)
			persisted = await thread_service.create_message(
				thread_id,
				create_in,
				session,
				principal=principal,
			)
			yield _sse_event(
				event="message_created",
				data=_message_to_sse_data(persisted),
			)

	except Exception:
		logger.exception("error during agent streaming")
		yield _sse_event(event="error", data={"message": "generation failed"})
		yield _sse_event(event="done", data={})
		return

	yield _sse_event(event="done", data={})


async def run_agent(
	agent: SDKAgent[AppContext],
	messages: list[SDKMessage],
	*,
	context: AppContext,
	system_prompt: str | None = None,
) -> list[SDKMessage]:
	"""run an agent against a list of messages.

	applies pre-filters before execution and post-filters after.

	args:
		agent: sdk Agent to run
		messages: input messages for the agent
		context: execution context
		system_prompt: optional system prompt to prepend

	returns:
		list of messages produced by the agent
	"""
	# prepend system prompt if provided
	if system_prompt:
		messages = [SDKSystemMessage.from_text(system_prompt), *messages]

	thread = SDKThread(messages=messages)
	result = await agent.run(thread, app_context=context, tool_choice="auto")
	produced: list[SDKMessage] = []
	for msg in result:
		produced.append(msg)

	return produced


async def run_agent_stream(
	agent: SDKAgent[AppContext],
	messages: list[SDKMessage],
	*,
	context: AppContext,
	system_prompt: str | None = None,
) -> AsyncIterator[AgentDelta]:
	"""run an agent in streaming mode.

	applies pre-filters before execution.

	args:
		agent: sdk Agent to run
		messages: input messages for the agent
		context: execution context
		system_prompt: optional system prompt to prepend

	yields:
		AgentDelta events as the agent produces output
	"""
	# prepend system prompt if provided
	if system_prompt:
		messages = [SDKSystemMessage.from_text(system_prompt), *messages]

	thread = SDKThread(messages=messages)
	stream = await agent.run(
		thread,
		app_context=context,
		tool_choice="auto",
		stream=True,
	)

	async for delta in stream:
		yield delta
