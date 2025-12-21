"""Agent class - orchestrates LLM with tools."""

from __future__ import annotations

from nokodo_ai.llm import LLM
from nokodo_ai.message import (
	AssistantMessage,
	ToolMessage,
	ToolResult,
	UserMessage,
)
from nokodo_ai.thread import Thread
from nokodo_ai.tool import Tool


class Agent:
	"""an agent that orchestrates an LLM with tools.

	agents can execute multi-step reasoning by:
	1. receiving user input
	2. calling the LLM to decide on actions
	3. executing tools when requested
	4. feeding tool results back to the LLM
	5. repeating until a final response is ready

	usage:
		from nokodo_ai import Agent, LLM, tool

		@tool(description="get current weather")
		async def get_weather(city: str) -> str:
			return f"sunny in {city}"

		agent = Agent(
			llm=LLM("gpt-4o"),
			tools=[get_weather],
			system_prompt="you are a helpful assistant",
		)

		response = await agent.run("what's the weather in paris?")
	"""

	def __init__(
		self,
		*,
		llm: LLM,
		tools: list[Tool] | None = None,
		system_prompt: str | None = None,
		max_iterations: int = 10,
	) -> None:
		"""initialize agent.

		args:
			llm: the LLM to use for reasoning
			tools: list of tools the agent can use
			system_prompt: optional system prompt
			max_iterations: maximum tool-use iterations before stopping
		"""
		self.llm = llm
		self.tools = {t.name: t for t in (tools or [])}
		self.system_prompt = system_prompt
		self.max_iterations = max_iterations

	async def run(
		self,
		user_input: str,
		*,
		thread: Thread | None = None,
	) -> AssistantMessage:
		"""run the agent with user input.

		args:
			user_input: the user's message
			thread: optional existing conversation thread

		returns:
			the agent's final response
		"""
		if thread is None:
			thread = Thread()

		# add system prompt if configured and thread is empty
		if self.system_prompt and not thread.messages:
			from nokodo_ai.message import SystemMessage

			thread.add(SystemMessage(content=self.system_prompt))

		# add user message
		thread.add(UserMessage(content=user_input))

		# run agent loop
		for _ in range(self.max_iterations):
			# get LLM response
			response = await self.llm.generate(thread.messages)
			thread.add(response)

			# check if we need to execute tools
			if not response.tool_calls:
				return response

			# execute requested tools
			tool_results = await self._execute_tools(response)
			thread.add(ToolMessage(tool_results=tool_results))

		# max iterations reached
		return AssistantMessage(
			content="I was unable to complete the task within the allowed steps."
		)

	async def _execute_tools(self, response: AssistantMessage) -> list[ToolResult]:
		"""execute all tool calls in a response."""
		results: list[ToolResult] = []

		for tool_call in response.tool_calls or []:
			tool = self.tools.get(tool_call.name)

			if tool is None:
				results.append(
					ToolResult(
						tool_call_id=tool_call.id,
						content=f"error: unknown tool '{tool_call.name}'",
						is_error=True,
					)
				)
				continue

			try:
				# parse arguments and execute
				import json

				args = json.loads(tool_call.arguments) if tool_call.arguments else {}
				result = await tool(**args)
				results.append(
					ToolResult(
						tool_call_id=tool_call.id,
						content=str(result),
					)
				)
			except Exception as e:
				results.append(
					ToolResult(
						tool_call_id=tool_call.id,
						content=f"error executing tool: {e}",
						is_error=True,
					)
				)

		return results
