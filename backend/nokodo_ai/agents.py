"""agent class - orchestrates chat model with tools."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Literal, overload

from pydantic import Field, SkipValidation, ValidationError

from .base import Base
from .chat_models import ChatModel
from .context import AgentContext, ToolCallContext
from .deltas import AgentDelta, ChatModelDelta
from .filters import Filter
from .hooks import Hook
from .messages import (
	PROVIDER_DATA_KEY,
	AssistantMessage,
	SystemMessage,
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
"""everything one agent run added to the thread, in order."""
type AgentToolChoice = Literal["auto", "none", "required"] | str | None
"""how the model may use tools this iteration, or one tool named to force."""


@dataclass(slots=True)
class AgentIterationState[AppContextT = None]:
	"""mutable state for one agent loop iteration."""

	thread: Thread
	"""the conversation as the model will see it this iteration."""
	tools: list[Tool[AppContextT]]
	"""tools offered this iteration."""
	# todo: if filters need context-aware model selection, move the chat model
	# set into iteration state instead of adding model params piecemeal.
	tool_choice: AgentToolChoice = "auto"
	"""how the model may use those tools."""
	iteration: int = 0
	"""how many iterations have already run, counting from zero."""

	def snapshot(self, final: bool = False) -> AgentIterationSnapshot[AppContextT]:
		"""return a read-only view for observers."""
		return AgentIterationSnapshot(
			thread=self.thread.model_copy(deep=True),
			tools=list(self.tools),
			tool_choice=self.tool_choice,
			iteration=self.iteration,
			final=final,
		)


@dataclass(frozen=True, slots=True)
class AgentIterationSnapshot[AppContextT = None]:
	"""read-only view of one agent loop iteration for hooks and tools.

	the thread is deep-copied and the tool list is a fresh list, so an observer
	cannot reshape the live loop; the ``Tool`` objects in it are the loop's own.
	filters receive ``AgentIterationState`` when they need to write loop state.
	"""

	thread: Thread
	"""a deep copy, so an observer cannot edit the live conversation."""
	tools: list[Tool[AppContextT]]
	"""the tools offered this iteration, in a list the observer owns."""
	tool_choice: AgentToolChoice
	"""how the model was allowed to use them."""
	iteration: int
	"""which iteration this snapshot was taken from."""
	final: bool = False
	"""whether the loop has finished, so this is the run's last snapshot."""


_cancel_tasks: set[asyncio.Task[None]] = set()
"""holds fire-and-forget provider-cancel tasks until they finish.

``asyncio.create_task`` keeps only a weak reference, so without this a cancel
could be collected before it ever reached the provider.
"""


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
		from nokodo_ai import (
			Agent,
			AgentContext,
			AgentIterationSnapshot,
			ChatModel,
			SystemMessage,
			Thread,
			ToolCallContext,
			ToolMessage,
			UserMessage,
			tool,
		)

		@tool(name="get_weather", description="get current weather")
		def get_weather(
			__state__: AgentIterationSnapshot[None],
			__agent_context__: AgentContext,
			__tool_call_context__: ToolCallContext,
			__app_context__: None,
			city: str,
		) -> ToolMessage:
			_ = (__state__, __agent_context__, __app_context__)
			return ToolMessage(
				tool_call_id=__tool_call_context__.tool_call_id,
				tool_output=f"sunny in {city}",
			)

		chat_model = ChatModel.create(
			"gpt-4o",
			adapter={"type": "openai", "api_key": "..."},
			temperature=0.7,
		)
		agent = Agent(chat_model=chat_model, tools=[get_weather])

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
	"""the model this agent generates with."""
	tools: list[SkipValidation[Tool[AppContextT]]] = Field(
		default_factory=list, description="list of tools the agent can use"
	)
	"""what the agent can call, offered to the model each iteration."""
	filters: list[SkipValidation[Filter[AppContextT]]] = Field(
		default_factory=list,
		description="pre-processing filters that can modify the thread",
	)
	"""run before each iteration and MAY rewrite loop state."""
	hooks: list[SkipValidation[Hook[AppContextT]]] = Field(
		default_factory=list,
		description="post-execution hooks for observation (read-only)",
	)
	"""observe each iteration and cannot change it; a failing one is logged."""
	max_iterations: int = Field(default=10, description="maximum Agent iterations")
	"""bounds the tool-calling loop, so it cannot run forever."""

	@overload
	async def run(
		self,
		thread: Thread,
		app_context: AppContextT | None = None,
		tool_choice: AgentToolChoice = "auto",
		stream: Literal[False] = False,
	) -> AgentProducedMessages:
		"""run to completion and return everything the agent produced."""
		...

	@overload
	async def run(
		self,
		thread: Thread,
		app_context: AppContextT | None = None,
		tool_choice: AgentToolChoice = "auto",
		stream: Literal[True] = True,
	) -> AsyncGenerator[AgentDelta]:
		"""run and yield deltas as the agent produces them."""
		...

	async def run(
		self,
		thread: Thread,
		app_context: AppContextT | None = None,
		tool_choice: AgentToolChoice = "auto",
		stream: bool = False,
	) -> AgentProducedMessages | AsyncGenerator[AgentDelta]:
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

		while True:
			agent_context = AgentContext(model=self.chat_model)
			state = await self._apply_filters(state, agent_context, app_context)

			if not _should_continue_agent_run(state):
				await self._execute_hooks(state, agent_context, app_context, final=True)
				return produced

			if model_calls >= self.max_iterations:
				break

			tool_choice_for_generation = state.tool_choice if state.tools else None
			assistant_response = await self.chat_model.generate(
				state.thread,
				tools=[tool.definition for tool in state.tools],
				tool_choice=tool_choice_for_generation,
			)
			# tool_choice is consumed for this iteration only; reset to "auto"
			# so a forced choice never carries into later iterations.
			state.tool_choice = "auto"
			model_calls += 1
			state.thread.add(assistant_response)
			produced.append(assistant_response)

			await self._execute_hooks(state, agent_context, app_context)

			for tool_call in assistant_response.tool_calls:
				tool_message = await self._execute_tools(
					tool_call=tool_call,
					state=state,
					agent_context=agent_context,
					app_context=app_context,
				)
				state.thread.add(tool_message)
				produced.append(tool_message)
			state.iteration += 1

		# max iterations reached. call chat model one more time without tools
		final_response = await self.chat_model.generate(
			state.thread,
			tools=[tool.definition for tool in state.tools],
			tool_choice="none",
		)
		if final_response.content or final_response.tool_calls:
			state.thread.add(final_response)
			produced.append(final_response)
		await self._execute_hooks(state, agent_context, app_context, final=True)

		return produced

	async def _run_stream(
		self,
		thread: Thread,
		app_context: AppContextT | None,
		tool_choice: AgentToolChoice = "auto",
	) -> AsyncGenerator[AgentDelta]:
		"""run the agent loop, yielding deltas as they are produced."""
		chunk_index = 0
		state = self._initial_iteration_state(thread, tool_choice)
		model_calls = 0

		while True:
			agent_context = AgentContext(model=self.chat_model)
			state = await self._apply_filters(state, agent_context, app_context)

			if not _should_continue_agent_run(state):
				await self._execute_hooks(state, agent_context, app_context, final=True)
				yield AgentDelta.done_sentinel(chunk_index=chunk_index)
				return

			if model_calls >= self.max_iterations:
				break

			tool_choice_for_generation = state.tool_choice if state.tools else None
			# stream from chat model and accumulate full message
			assistant_message = AssistantMessage()
			terminal_delta: ChatModelDelta | None = None
			async for chat_delta in self._stream_with_cancel(
				state.thread,
				tools=[tool.definition for tool in state.tools],
				tool_choice=tool_choice_for_generation,
				accumulated=assistant_message,
			):
				# accumulate into complete message for thread
				assistant_message = assistant_message.merge(chat_delta.message)
				if chat_delta.done:
					terminal_delta = chat_delta
					continue
				yield AgentDelta(chat=chat_delta, chunk_index=chunk_index)
				chunk_index += 1

			# add completed message to thread
			model_calls += 1
			# tool_choice is consumed for this iteration only; reset to "auto"
			# so a forced choice never carries into later iterations.
			state.tool_choice = "auto"
			if terminal_delta is not None:
				terminal_delta.message.finish_reason = assistant_message.finish_reason
				yield AgentDelta(chat=terminal_delta, chunk_index=chunk_index)
				chunk_index += 1
			state.thread.add(assistant_message)

			await self._execute_hooks(state, agent_context, app_context)

			# execute each tool call
			for tool_call in assistant_message.tool_calls:
				tool_message = await self._execute_tools(
					tool_call=tool_call,
					state=state,
					agent_context=agent_context,
					app_context=app_context,
				)
				state.thread.add(tool_message)
				yield AgentDelta(tool=tool_message, chunk_index=chunk_index)
				chunk_index += 1
			state.iteration += 1

		# max iterations reached - final call without tools
		final_message = AssistantMessage()
		terminal_delta: ChatModelDelta | None = None
		async for chat_delta in self._stream_with_cancel(
			state.thread,
			tools=[tool.definition for tool in state.tools],
			tool_choice="none",
			accumulated=final_message,
		):
			final_message = final_message.merge(chat_delta.message)
			if chat_delta.done:
				terminal_delta = chat_delta
				continue
			yield AgentDelta(chat=chat_delta, chunk_index=chunk_index)
			chunk_index += 1

		has_content = bool(final_message.content or final_message.tool_calls)
		# the terminal delta closes the stream on the same terms as the main
		# loop: an empty final answer is still an answer that ended, and
		# withholding its `done` strands every consumer waiting for one.
		if terminal_delta is not None:
			terminal_delta.message.finish_reason = final_message.finish_reason
			yield AgentDelta(chat=terminal_delta, chunk_index=chunk_index)
			chunk_index += 1
		if has_content:
			state.thread.add(final_message)

		await self._execute_hooks(state, agent_context, app_context, final=True)
		yield AgentDelta.done_sentinel(chunk_index=chunk_index)

	async def _execute_hooks(
		self,
		state: AgentIterationState[AppContextT],
		agent_context: AgentContext,
		app_context: AppContextT | None,
		final: bool = False,
	) -> None:
		"""execute hooks with a read-only snapshot of the current run state."""
		snapshot = state.snapshot(final=final)
		for hook in self.hooks:
			try:
				await hook.execute(
					snapshot,
					agent_context=agent_context,
					app_context=app_context,
				)
			except Exception:
				logger.exception("agent observer hook failed: %s", hook.name)

	async def _stream_with_cancel(
		self,
		thread: Thread,
		tools: list[ToolDefinition],
		tool_choice: AgentToolChoice,
		accumulated: AssistantMessage,
	) -> AsyncGenerator[ChatModelDelta]:
		"""stream chat model deltas; notify provider on any non-natural exit.

		``accumulated`` is merged by the CALLER, not here: this only holds the
		reference so a cancel can report whatever had arrived by then.

		when the loop exits without observing a final ``done`` delta -
		cancellation, downstream exception, ``aclose`` from the consumer, or any
		other unclean termination - passes the accumulated message to
		``ChatModel.cancel_generation`` fire-and-forget so the adapter can
		extract its provider run id and stop the generation server-side.

		when the provider stream ends naturally (last delta has ``done=True``)
		no cancel notification is issued - the run completed on its own.

		:param thread: the conversation thread.
		:param tools: tool definitions available for this call.
		:param tool_choice: tool selection strategy.
		"""
		completed_naturally = False
		try:
			async for chat_delta in self.chat_model.generate(
				thread,
				stream=True,
				tools=tools,
				tool_choice=tool_choice,
			):
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
			state = await filter_.process(
				state,
				agent_context=agent_context,
				app_context=app_context,
			)
		return state

	async def _execute_tools(
		self,
		tool_call: ToolCall,
		state: AgentIterationState[AppContextT],
		agent_context: AgentContext,
		app_context: AppContextT | None,
	) -> ToolMessage:
		"""execute a single tool call and return the result."""
		# look up tool first so error messages can include expected schema
		tool = next((tool for tool in state.tools if tool.name == tool_call.name), None)
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
		tool_ctx = ToolCallContext(
			tool_call_id=tool_call.id,
			tool_call_start_time=tool_call.created_at_monotonic,
			metadata=(tool_call.metadata or {}).copy(),
		)

		# execute
		try:
			tool_message = await tool.call(
				state.snapshot(),
				agent_context,
				tool_ctx,
				app_context,
				**args,
			)
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
