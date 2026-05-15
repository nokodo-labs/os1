"""agent class - orchestrates chat model with tools."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, overload

from pydantic import Field, SkipValidation, ValidationError

from .base import Base
from .chat_models import ChatModel
from .context import AgentContext
from .deltas import AgentDelta, ChatModelDelta
from .filters import Filter
from .hooks import Hook
from .messages import (
	PROVIDER_DATA_KEY,
	AssistantMessage,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from .threads import Thread
from .tool import Tool, ToolDefinition
from .types.json import JSONObject
from .utils.dicts import deep_merge


logger = logging.getLogger(__name__)

AgentProducedMessages = list[AssistantMessage | ToolMessage]
type AgentToolChoice = Literal["auto", "none", "required"] | str | None


@dataclass(slots=True)
class AgentIterationState[AppContextT = None]:
	"""mutable state for one agent loop iteration."""

	thread: Thread
	tools: list[Tool[AppContextT]]
	# todo: if filters need context-aware model selection, move the chat model
	# set into iteration state instead of adding model params piecemeal.
	tool_choice: AgentToolChoice = "auto"


# strong references to fire-and-forget cancel tasks so the event loop does
# not GC them before they have a chance to call the provider cancel API.
# python 3.12+ keeps only weak references from asyncio.create_task().
_cancel_tasks: set[asyncio.Task[None]] = set()


def _should_continue_agent_run[AppContextT](
	state: AgentIterationState[AppContextT],
) -> bool:
	"""return whether this thread state needs another model call."""
	thread = state.thread
	for message in reversed(thread.messages):
		if isinstance(message, SystemMessage):
			continue
		if isinstance(message, (UserMessage, ToolMessage)):
			return True
		if isinstance(message, AssistantMessage):
			return bool(message.tool_calls)
	return True


class Agent[AppContextT = None](Base):
	"""an agent that orchestrates a chat model with tools.

	agents are generic over AppContextT to allow application-specific
	context to be passed through the entire execution pipeline.

	agents can execute multi-step reasoning by:
	1. receiving a thread with messages (including system prompt if needed)
	2. running pre-filters to augment/modify input
	3. calling the chat model to decide on actions
	4. running post-filters on responses
	5. executing tools when requested
	6. feeding tool results back to the chat model
	7. repeating until a final response is ready

	chat model configuration (temperature, max_tokens, etc.) belongs in the ChatModel.
	system prompts belong in the Thread as a SystemMessage.

	usage:
		from nokodo_ai import Agent, ChatModel, Tool
		from nokodo_ai.message import SystemMessage, UserMessage
		from nokodo_ai.thread import Thread

		class WeatherTool(Tool[None]):
			name = "get_weather"
			description = "get current weather"

			async def call(self, agent_ctx, app_ctx, city: str) -> ToolMessage:
				return self.success(f"sunny in {city}", agent_ctx)

		chat_model = ChatModel.create(
			"gpt-4o",
			adapter={"type": "openai", "api_key": "..."},
			temperature=0.7,
		)
		agent = Agent(chat_model=chat_model, tools=[WeatherTool()])

		thread = Thread()
		thread.add(SystemMessage.from_text("you are a helpful assistant"))
		thread.add(UserMessage.from_text("what's the weather in paris?"))

		# non-streaming
		messages = await agent.run(thread)

		# streaming
		async for delta in agent.run(thread, stream=True):
			print(delta)
	"""

	chat_model: ChatModel = Field(
		..., description="which model to use for Agent execution"
	)
	tools: list[SkipValidation[Tool[AppContextT]]] = Field(
		default_factory=list, description="list of tools the agent can use"
	)
	filters: list[SkipValidation[Filter[AppContextT]]] = Field(
		default_factory=list,
		description="pre-processing filters that can modify the thread",
	)
	hooks: list[SkipValidation[Hook[AppContextT]]] = Field(
		default_factory=list,
		description="post-execution hooks for observation (read-only)",
	)
	max_iterations: int = Field(default=10, description="maximum Agent iterations")

	@property
	def tools_map(self) -> dict[str, Tool[AppContextT]]:
		"""map of tool names to tool instances for fast lookup."""
		return {t.name: t for t in self.tools}

	@property
	def tool_definitions(self) -> list[ToolDefinition]:
		"""get tool definitions for chat_model.generate() calls."""
		return [t.definition for t in self.tools]

	@overload
	async def run(
		self,
		thread: Thread,
		app_context: AppContextT | None = None,
		tool_choice: AgentToolChoice = "auto",
		stream: Literal[False] = False,
	) -> AgentProducedMessages: ...

	@overload
	async def run(
		self,
		thread: Thread,
		app_context: AppContextT | None = None,
		tool_choice: AgentToolChoice = "auto",
		stream: Literal[True] = True,
	) -> AsyncIterator[AgentDelta]: ...

	async def run(
		self,
		thread: Thread,
		app_context: AppContextT | None = None,
		tool_choice: AgentToolChoice = "auto",
		stream: bool = False,
	) -> AgentProducedMessages | AsyncIterator[AgentDelta]:
		"""run the agent against a thread.

		the thread should already contain any system prompt and user messages.
		chat model configuration (temperature, max_tokens) is taken from the ChatModel.

		args:
			thread: the conversation thread to continue
			app_context: application-specific context passed to tools and filters
			tool_choice: how to select tools - "auto", "none", "required",
				or a specific tool name
			stream: if True, yields messages as they are produced

		note on out-of-band injection: to inject user messages into a running
		agent loop (e.g. run-steering), add a ``SteeringFilter`` to
		``self.filters`` before calling ``run``. filters run at every iteration
		boundary and can drain external inboxes into the thread.

		returns:
			list of messages produced during this run (non-streaming), or
			an async iterator yielding messages as they are produced (streaming)
		"""
		if stream:
			return self._run_stream(
				thread,
				app_context,
				tool_choice=tool_choice,
			)
		return await self._run_sync(
			thread=thread,
			app_context=app_context,
			tool_choice=tool_choice,
		)

	async def _run_sync(
		self,
		thread: Thread,
		app_context: AppContextT | None,
		tool_choice: AgentToolChoice = "auto",
	) -> AgentProducedMessages:
		"""run the agent loop synchronously, returning all produced messages."""
		produced: AgentProducedMessages = []
		state = self._initial_iteration_state(thread, tool_choice)
		model_calls = 0
		iteration = 0

		while True:
			agent_context = AgentContext(
				thread=state.thread,
				model=self.chat_model,
				iteration=iteration,
			)
			state = await self._apply_filters(state, agent_context, app_context)
			self.tools = state.tools

			if not _should_continue_agent_run(state):
				return produced

			if model_calls >= self.max_iterations:
				break

			tool_choice_for_generation = state.tool_choice if self.tools else None
			assistant_response = await self.chat_model.generate(
				state.thread,
				tools=self.tool_definitions,
				tool_choice=tool_choice_for_generation,
			)
			model_calls += 1
			state.thread.add(assistant_response)
			produced.append(assistant_response)

			# execute hooks after response (read-only observation)
			for hook in self.hooks:
				await hook.execute(
					state.thread,
					agent_context=agent_context,
					app_context=app_context,
				)

			for tool_call in assistant_response.tool_calls:
				tool_message = await self._execute_tools(
					tool_call=tool_call,
					agent_context=agent_context,
					app_context=app_context,
				)
				state.thread.add(tool_message)
				produced.append(tool_message)
			iteration += 1

		# max iterations reached. call chat model one more time without tools
		final_response = await self.chat_model.generate(
			state.thread,
			tools=self.tool_definitions,
			tool_choice="none",
		)
		state.thread.add(final_response)
		produced.append(final_response)

		return produced

	async def _run_stream(
		self,
		thread: Thread,
		app_context: AppContextT | None,
		tool_choice: AgentToolChoice = "auto",
	) -> AsyncIterator[AgentDelta]:
		"""run the agent loop, yielding deltas as they are produced."""
		chunk_index = 0
		state = self._initial_iteration_state(thread, tool_choice)
		model_calls = 0
		iteration = 0

		while True:
			agent_context = AgentContext(
				thread=state.thread,
				model=self.chat_model,
				iteration=iteration,
			)
			state = await self._apply_filters(state, agent_context, app_context)
			self.tools = state.tools

			if not _should_continue_agent_run(state):
				yield AgentDelta.done_sentinel(chunk_index=chunk_index)
				return

			if model_calls >= self.max_iterations:
				break

			tool_choice_for_generation = state.tool_choice if self.tools else None
			# stream from chat model and accumulate full message
			assistant_message = AssistantMessage()
			async for chat_delta in self._stream_with_cancel(
				state.thread,
				tools=self.tool_definitions,
				tool_choice=tool_choice_for_generation,
			):
				# accumulate into complete message for thread
				assistant_message = assistant_message.merge(chat_delta.message)

				# yield as agent delta
				yield AgentDelta(chat=chat_delta, chunk_index=chunk_index)
				chunk_index += 1

			# add completed message to thread
			model_calls += 1
			state.thread.add(assistant_message)

			# execute hooks (read-only observation)
			for hook in self.hooks:
				await hook.execute(
					state.thread,
					agent_context=agent_context,
					app_context=app_context,
				)

			# execute each tool call
			for tool_call in assistant_message.tool_calls:
				tool_message = await self._execute_tools(
					tool_call=tool_call,
					agent_context=agent_context,
					app_context=app_context,
				)
				state.thread.add(tool_message)
				yield AgentDelta(tool=tool_message, chunk_index=chunk_index)
				chunk_index += 1
			iteration += 1

		# max iterations reached - final call without tools
		final_message = AssistantMessage()
		async for chat_delta in self._stream_with_cancel(
			state.thread,
			tools=self.tool_definitions,
			tool_choice="none",
		):
			final_message = final_message.merge(chat_delta.message)
			yield AgentDelta(chat=chat_delta, chunk_index=chunk_index)
			chunk_index += 1

		state.thread.add(final_message)

		# add fallback text if empty
		if not final_message.text:
			final_message.content.append(
				TextContent(
					text="I was unable to complete the task within the allowed steps."
				)
			)

		yield AgentDelta.done_sentinel(chunk_index=chunk_index)

	async def _stream_with_cancel(
		self,
		thread: Thread,
		tools: list[ToolDefinition],
		tool_choice: AgentToolChoice,
	) -> AsyncIterator[ChatModelDelta]:
		"""stream chat model deltas; notify provider on any non-natural exit.

		accumulates the ``AssistantMessage`` from streaming deltas. when the
		loop exits without observing a final ``done`` delta - cancellation,
		downstream exception, ``aclose`` from the consumer, or any other
		unclean termination - passes the accumulated message to
		``ChatModel.cancel_generation`` fire-and-forget so the adapter can
		extract its provider run id and stop the generation server-side.

		when the provider stream ends naturally (last delta has ``done=True``)
		no cancel notification is issued - the run completed on its own.

		:param thread: the conversation thread.
		:param tools: tool definitions available for this call.
		:param tool_choice: tool selection strategy.
		"""
		accumulated = AssistantMessage()
		completed_naturally = False
		try:
			async for chat_delta in self.chat_model.generate(
				thread,
				stream=True,
				tools=tools,
				tool_choice=tool_choice,
			):
				accumulated = accumulated.merge(chat_delta.message)
				yield chat_delta
				if chat_delta.done:
					completed_naturally = True
		finally:
			if not completed_naturally:
				# fire-and-forget: don't block whatever caused the early exit
				# (cancel, exception, aclose) on a slow provider cancel call.
				cancel_task = asyncio.create_task(
					self._safe_cancel_generation(accumulated),
					name="chat_model_cancel_generation",
				)
				# strong-ref pattern - python 3.12+ may GC unreferenced tasks
				# before they run. keep the ref until done.
				_cancel_tasks.add(cancel_task)
				cancel_task.add_done_callback(_cancel_tasks.discard)

	async def _safe_cancel_generation(self, latest_message: AssistantMessage) -> None:
		"""best-effort cancel; swallows exceptions."""
		try:
			await self.chat_model.cancel_generation(latest_message)
		except Exception:
			logger.debug("provider cancel_generation raised", exc_info=True)

	def _initial_iteration_state(
		self,
		thread: Thread,
		tool_choice: AgentToolChoice,
	) -> AgentIterationState[AppContextT]:
		"""build the starting state for an agent run."""
		return AgentIterationState(
			thread=thread,
			tools=self.tools,
			tool_choice=tool_choice,
		)

	async def _apply_filters(
		self,
		state: AgentIterationState[AppContextT],
		agent_context: AgentContext,
		app_context: AppContextT | None,
	) -> AgentIterationState[AppContextT]:
		"""apply pre-model filters to iteration state."""
		for filter_ in self.filters:
			agent_context.thread = state.thread
			state = await filter_.process(
				state,
				agent_context=agent_context,
				app_context=app_context,
			)
		agent_context.thread = state.thread
		return state

	async def _execute_tools(
		self,
		tool_call: ToolCall,
		agent_context: AgentContext,
		app_context: AppContextT | None,
	) -> ToolMessage:
		"""execute a single tool call and return the result."""
		# look up tool first so error messages can include expected schema
		tool = self.tools_map.get(tool_call.name)
		if tool is None:
			return ToolMessage(
				tool_call_id=tool_call.id,
				tool_output=f"error: unknown tool '{tool_call.name}'",
				is_error=True,
				metadata=tool_call.metadata,
			)

		# parse arguments
		raw_args = tool_call.arguments
		args: JSONObject

		if isinstance(raw_args, dict):
			args = raw_args
		elif isinstance(raw_args, str):
			try:
				parsed = json.loads(raw_args)
			except json.JSONDecodeError as e:
				hint = json.dumps(tool.parameters, indent=2)
				return ToolMessage(
					tool_call_id=tool_call.id,
					tool_output=(
						f"could not parse arguments. invalid json: {e}\n\n"
						f"expected parameters:\n{hint}"
					),
					is_error=True,
					metadata=tool_call.metadata,
				)
			if not isinstance(parsed, dict):
				return ToolMessage(
					tool_call_id=tool_call.id,
					tool_output="could not parse arguments. expected a json object",
					is_error=True,
					metadata=tool_call.metadata,
				)
			args = parsed
		else:
			return ToolMessage(
				tool_call_id=tool_call.id,
				tool_output=(
					"could not parse arguments. expected json object or json string"
				),
				is_error=True,
				metadata=tool_call.metadata,
			)

		# create tool-specific context
		tool_ctx = AgentContext(
			thread=agent_context.thread,
			model=agent_context.model,
			tool_call_id=tool_call.id,
			iteration=agent_context.iteration,
			retry_count=agent_context.retry_count,
			tool_call_start_time=tool_call.created_at_monotonic,
			metadata=tool_call.metadata or {},
		)

		# execute
		try:
			tool_message = await tool.call(tool_ctx, app_context, **args)
		except (ValidationError, TypeError) as e:
			logger.warning("invalid arguments for tool %s: %s", tool.name, e)
			hint = json.dumps(tool.parameters, indent=2)
			return ToolMessage(
				tool_call_id=tool_call.id,
				tool_output=(
					f"invalid arguments for tool '{tool.name}': {e}\n\n"
					f"expected parameters:\n{hint}"
				),
				is_error=True,
				metadata=tool_call.metadata,
			)
		except Exception:
			logger.exception("unhandled error executing tool %s", tool.name)
			return ToolMessage(
				tool_call_id=tool_call.id,
				tool_output="an internal error occurred while executing this tool",
				is_error=True,
				metadata=tool_call.metadata,
			)

		# ensure ToolMessage carries the provider tool_call id metadata (e.g. openai)
		# even if the concrete tool returned a ToolMessage without metadata.
		tool_call_pd = (tool_call.metadata or {}).get(PROVIDER_DATA_KEY)
		if isinstance(tool_call_pd, dict):
			tool_msg_pd = (tool_message.metadata or {}).get(PROVIDER_DATA_KEY)
			if isinstance(tool_msg_pd, dict):
				merged_pd = deep_merge(tool_msg_pd, tool_call_pd, overwrite=False)
			else:
				merged_pd = tool_call_pd
			tool_message.metadata = tool_message.metadata or {}
			tool_message.metadata[PROVIDER_DATA_KEY] = merged_pd

		return tool_message
