"""Agent class - orchestrates LLM with tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from nokodo_ai.chat_models import ChatModel
from nokodo_ai.message import (
	AssistantMessage,
	SystemMessage,
	TextContent,
	ToolMessage,
	ToolResult,
	UserMessage,
)
from nokodo_ai.thread import Thread
from nokodo_ai.tool import Tool, ToolExecutionContext
from nokodo_ai.types.json import JSONObject


if TYPE_CHECKING:
	from collections.abc import Callable


class Agent:
	"""an agent that orchestrates an LLM with tools.

	agents can execute multi-step reasoning by:
	1. receiving user input
	2. calling the LLM to decide on actions
	3. executing tools when requested
	4. feeding tool results back to the LLM
	5. repeating until a final response is ready

	usage:
		from nokodo_ai import Agent, ChatModel, tool

		@tool(description="get current weather")
		async def get_weather(city: str) -> str:
			return f"sunny in {city}"

		agent = Agent(
			llm=ChatModel("gpt-4o"),
			tools=[get_weather],
			system_prompt="you are a helpful assistant",
		)

		response = await agent.run("what's the weather in paris?")
	"""

	def __init__(
		self,
		*,
		llm: ChatModel,
		tools: list[Tool] | None = None,
		system_prompt: str | None = None,
		max_iterations: int = 10,
		on_tool_call: Callable[[str, str, JSONObject], None] | None = None,
		on_tool_result: Callable[[str, str, bool], None] | None = None,
	) -> None:
		"""initialize agent.

		args:
			llm: the LLM to use for reasoning
			tools: list of tools the agent can use
			system_prompt: optional system prompt
			max_iterations: maximum tool-use iterations before stopping
			on_tool_call: callback when a tool is called (tool_name, tool_call_id, args)
			on_tool_result: callback when tool returns (tool_call_id, result, is_error)
		"""
		self.llm = llm
		self.tools = {t.name: t for t in (tools or [])}
		self.tools_list = tools or []
		self.system_prompt = system_prompt
		self.max_iterations = max_iterations
		self.on_tool_call = on_tool_call
		self.on_tool_result = on_tool_result

	async def run(
		self,
		user_input: str,
		*,
		thread: Thread | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
	) -> AssistantMessage:
		"""run the agent with user input.

		args:
			user_input: the user's message
			thread: optional existing conversation thread
			tool_choice: how to select tools - "auto", "none", "required",
				or a specific tool name

		returns:
			the agent's final response
		"""
		if thread is None:
			thread = Thread()

		# add system prompt if configured and thread is empty
		if self.system_prompt and not thread.messages:
			thread.add(SystemMessage.from_text(self.system_prompt))

		# add user message
		thread.add(UserMessage.from_text(user_input))

		# run agent loop
		for iteration in range(self.max_iterations):
			# determine tool_choice for this iteration
			current_tool_choice = tool_choice if self.tools_list else None

			# get LLM response
			response = await self.llm.generate(
				thread,
				tools=self.tools_list if self.tools_list else None,
				tool_choice=current_tool_choice,
			)
			thread.add(response)

			# check if we need to execute tools
			if not response.tool_calls:
				return response

			# execute requested tools
			tool_messages = await self._execute_tools(thread, response)
			for tool_message in tool_messages:
				thread.add(tool_message)

		# max iterations reached - call LLM one more time without tools
		final_response = await self.llm.generate(
			thread,
			tools=None,
			tool_choice=None,
		)
		thread.add(final_response)

		# if still no text content, add a fallback message
		if not final_response.text:
			final_response.content.append(
				TextContent(
					text="I was unable to complete the task within the allowed steps."
				)
			)

		return final_response

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

			# notify callback if set
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
