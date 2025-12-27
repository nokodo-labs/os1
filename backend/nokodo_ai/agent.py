"""agent class - orchestrates llm with tools."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Literal

from nokodo_ai.chat_models import ChatModel
from nokodo_ai.message import (
	AssistantMessage,
	Message,
	TextContent,
	ToolMessage,
	ToolResult,
)
from nokodo_ai.thread import Thread
from nokodo_ai.tool import Tool, ToolExecutionContext
from nokodo_ai.types.json import JSONObject


if TYPE_CHECKING:
	from collections.abc import Callable


class Agent:
	"""an agent that orchestrates an llm with tools.

	agents can execute multi-step reasoning by:
	1. receiving a thread with messages (including system prompt if needed)
	2. calling the llm to decide on actions
	3. executing tools when requested
	4. feeding tool results back to the llm
	5. repeating until a final response is ready

	llm configuration (temperature, max_tokens, etc.) belongs in the ChatModel.
	system prompts belong in the Thread as a SystemMessage.

	usage:
		from nokodo_ai import Agent, ChatModel, tool
		from nokodo_ai.message import SystemMessage, UserMessage
		from nokodo_ai.thread import Thread

		@tool(description="get current weather")
		async def get_weather(city: str) -> str:
			return f"sunny in {city}"

		llm = ChatModel("gpt-4o", temperature=0.7)
		agent = Agent(llm=llm, tools=[get_weather])

		thread = Thread()
		thread.add(SystemMessage.from_text("you are a helpful assistant"))
		thread.add(UserMessage.from_text("what's the weather in paris?"))

		# non-streaming
		messages = await agent.run(thread)

		# streaming
		async for message in agent.run(thread, stream=True):
			print(message)
	"""

	def __init__(
		self,
		*,
		llm: ChatModel,
		tools: list[Tool] | None = None,
		max_iterations: int = 10,
		on_tool_call: Callable[[str, str, JSONObject], None] | None = None,
		on_tool_result: Callable[[str, str, bool], None] | None = None,
	) -> None:
		"""initialize agent.

		args:
			llm: the ChatModel to use for reasoning (includes temp/max_tokens config)
			tools: list of tools the agent can use
			max_iterations: maximum tool-use iterations before stopping
			on_tool_call: callback when a tool is called (tool_name, tool_call_id, args)
			on_tool_result: callback when tool returns (tool_call_id, result, is_error)
		"""
		self.llm = llm
		self.tools = {t.name: t for t in (tools or [])}
		self.tools_list = tools or []
		self.max_iterations = max_iterations
		self.on_tool_call = on_tool_call
		self.on_tool_result = on_tool_result

	async def run(
		self,
		thread: Thread,
		*,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		stream: bool = False,
	) -> list[Message] | AsyncIterator[Message]:
		"""run the agent against a thread.

		the thread should already contain any system prompt and user messages.
		llm configuration (temperature, max_tokens) is taken from the ChatModel.

		args:
			thread: the conversation thread to continue
			tool_choice: how to select tools - "auto", "none", "required",
				or a specific tool name
			stream: if True, yields messages as they are produced

		returns:
			list of messages produced during this run (non-streaming), or
			an async iterator yielding messages as they are produced (streaming)
		"""
		if stream:
			return self._run_stream(thread, tool_choice=tool_choice)
		return await self._run_sync(thread, tool_choice=tool_choice)

	async def _run_sync(
		self,
		thread: Thread,
		*,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
	) -> list[Message]:
		"""run the agent loop synchronously, returning all produced messages."""
		produced: list[Message] = []

		for _iteration in range(self.max_iterations):
			current_tool_choice = tool_choice if self.tools_list else None

			response = await self.llm.generate(
				thread,
				tools=self.tools_list if self.tools_list else None,
				tool_choice=current_tool_choice,
			)
			thread.add(response)
			produced.append(response)

			if not response.tool_calls:
				return produced

			tool_messages = await self._execute_tools(thread, response)
			for tool_message in tool_messages:
				thread.add(tool_message)
				produced.append(tool_message)

		# max iterations reached - call llm one more time without tools
		final_response = await self.llm.generate(
			thread,
			tools=None,
			tool_choice=None,
		)
		thread.add(final_response)
		produced.append(final_response)

		if not final_response.text:
			final_response.content.append(
				TextContent(
					text="I was unable to complete the task within the allowed steps."
				)
			)

		return produced

	async def _run_stream(
		self,
		thread: Thread,
		*,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
	) -> AsyncIterator[Message]:
		"""run the agent loop, yielding messages as they are produced."""
		for _iteration in range(self.max_iterations):
			current_tool_choice = tool_choice if self.tools_list else None

			response = await self.llm.generate(
				thread,
				tools=self.tools_list if self.tools_list else None,
				tool_choice=current_tool_choice,
			)
			thread.add(response)
			yield response

			if not response.tool_calls:
				return

			tool_messages = await self._execute_tools(thread, response)
			for tool_message in tool_messages:
				thread.add(tool_message)
				yield tool_message

		# max iterations reached - call llm one more time without tools
		final_response = await self.llm.generate(
			thread,
			tools=None,
			tool_choice=None,
		)
		thread.add(final_response)

		if not final_response.text:
			final_response.content.append(
				TextContent(
					text="I was unable to complete the task within the allowed steps."
				)
			)

		yield final_response

	async def _execute_tools(
		self,
		thread: Thread,
		response: AssistantMessage,
	) -> list[ToolMessage]:
		"""execute all tool calls in a response."""
		messages: list[ToolMessage] = []

		for tool_call in response.tool_calls or []:
			tool = self.tools.get(tool_call.name)
			args: JSONObject = tool_call.arguments

			if self.on_tool_call:
				self.on_tool_call(tool_call.name, tool_call.id, args)

			if tool is None:
				result = ToolResult(
					tool_call_id=tool_call.id,
					output=f"error: unknown tool '{tool_call.name}'",
					is_error=True,
				)
				if self.on_tool_result:
					self.on_tool_result(tool_call.id, result.output, True)
				messages.append(ToolMessage(tool_result=result))
				continue

			try:
				context = ToolExecutionContext(call_id=tool_call.id, thread=thread)
				output = await tool.call(__context=context, **args)
				result = ToolResult(
					tool_call_id=tool_call.id,
					output=str(output),
				)
				if self.on_tool_result:
					self.on_tool_result(tool_call.id, result.output, False)
				messages.append(ToolMessage(tool_result=result))
			except Exception as e:
				result = ToolResult(
					tool_call_id=tool_call.id,
					output=f"error executing tool: {e}",
					is_error=True,
				)
				if self.on_tool_result:
					self.on_tool_result(tool_call.id, result.output, True)
				messages.append(ToolMessage(tool_result=result))

		return messages
