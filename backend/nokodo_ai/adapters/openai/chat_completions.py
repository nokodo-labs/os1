"""openai chat completions adapter - /v1/chat/completions endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

import openai

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.types import (
	OpenAIChatCompletionAssistantMessageParam,
	OpenAIChatCompletionFunctionDefinition,
	OpenAIChatCompletionFunctionToolCall,
	OpenAIChatCompletionFunctionToolCallParam,
	OpenAIChatCompletionMessageParam,
	OpenAIChatCompletionResponseFormatJSONSchema,
	OpenAIChatCompletionSystemMessageParam,
	OpenAIChatCompletionToolChoiceOptionParam,
	OpenAIChatCompletionToolMessageParam,
	OpenAIChatCompletionToolParam,
	OpenAIChatCompletionUserMessageParam,
)
from nokodo_ai.message import (
	AssistantMessage,
	ContentPart,
	JsonContent,
	RefusalContent,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	Usage,
	UserMessage,
)
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


if TYPE_CHECKING:
	from nokodo_ai.message import Message


class OpenAIChatCompletionsAdapter(BaseOpenAIAdapter, BaseChatAdapter):
	"""adapter for openai's /v1/chat/completions endpoint.

	this is the standard openai chat API used by most applications.
	"""

	def __init__(
		self,
		*,
		model: str = "gpt-4o",
		api_key: str | None = None,
		base_url: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize chat completions adapter.

		args:
			model: model identifier (e.g., "gpt-4o", "gpt-4o-mini")
			api_key: openai API key
			base_url: custom base URL
			timeout: request timeout in seconds
		"""
		super().__init__(api_key=api_key, base_url=base_url, timeout=timeout)
		self.model = model

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[False] = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[True],
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		*,
		stream: bool = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		if stream:
			return self._generate_streaming(
				messages,
				tools=tools,
				tool_choice=tool_choice,
				response_model=response_model,
				temperature=temperature,
				max_tokens=max_tokens,
			)
		return self._generate_once(
			messages,
			tools=tools,
			tool_choice=tool_choice,
			response_model=response_model,
			temperature=temperature,
			max_tokens=max_tokens,
		)

	async def _generate_once(
		self,
		messages: list[Message],
		*,
		tools: list[Tool] | None,
		tool_choice: Literal["auto", "none", "required"] | str | None,
		response_model: JSONObject | None,
		temperature: float | None,
		max_tokens: int | None,
	) -> AssistantMessage:
		"""generate a completion using /v1/chat/completions."""
		client = self._get_client()
		openai_messages = _messages_to_openai_chat_completions(messages)

		openai_tools = openai.omit
		openai_tool_choice = openai.omit
		if tools:
			openai_tools = _tools_to_openai(tools)
			if tool_choice is not None:
				openai_tool_choice = _tool_choice_to_openai(tool_choice)

		response_format = openai.omit
		if response_model:
			response_format = OpenAIChatCompletionResponseFormatJSONSchema(
				type="json_schema",
				json_schema={
					"name": "response",
					"strict": True,
					"schema": dict[str, object](response_model),
				},
			)

		openai_temperature = temperature if temperature is not None else openai.omit
		openai_max_tokens = max_tokens if max_tokens is not None else openai.omit

		response = await client.chat.completions.create(
			model=self.model,
			messages=openai_messages,
			max_tokens=openai_max_tokens,
			response_format=response_format,
			temperature=openai_temperature,
			tool_choice=openai_tool_choice,
			tools=openai_tools,
		)
		if not response.choices:
			return AssistantMessage(content=[TextContent(text="")])

		openai_message = response.choices[0].message

		# build content parts
		content: list[ContentPart] = []

		# handle structured output (response_format with json_schema)
		if response_model and openai_message.content:
			try:
				parsed = json.loads(openai_message.content)
				content.append(JsonContent(data=parsed))
			except json.JSONDecodeError:
				content.append(TextContent(text=openai_message.content))
		elif openai_message.content:
			content.append(TextContent(text=openai_message.content))

		# handle refusal
		if hasattr(openai_message, "refusal") and openai_message.refusal:
			content.append(RefusalContent(reason=openai_message.refusal))

		# handle tool calls
		tool_calls: list[ToolCall] = []
		if openai_message.tool_calls:
			for tool_call in openai_message.tool_calls:
				if isinstance(tool_call, OpenAIChatCompletionFunctionToolCall):
					args, metadata = _try_parse_tool_arguments(
						tool_call.function.arguments
					)
					tool_calls.append(
						ToolCall(
							id=tool_call.id,
							name=tool_call.function.name,
							arguments=args,
							metadata=metadata,
						)
					)

		# build usage
		usage: Usage | None = None
		if response.usage:
			usage = Usage(
				input_tokens=response.usage.prompt_tokens,
				output_tokens=response.usage.completion_tokens,
				total_tokens=response.usage.total_tokens,
			)

		return AssistantMessage(content=content, tool_calls=tool_calls, usage=usage)

	async def _generate_streaming(
		self,
		messages: list[Message],
		*,
		tools: list[Tool] | None,
		tool_choice: Literal["auto", "none", "required"] | str | None,
		response_model: JSONObject | None,
		temperature: float | None,
		max_tokens: int | None,
	) -> AsyncIterator[AssistantMessage]:
		"""stream a completion using /v1/chat/completions."""
		client = self._get_client()
		openai_messages = _messages_to_openai_chat_completions(messages)

		openai_tools = openai.omit
		openai_tool_choice = openai.omit
		if tools:
			openai_tools = _tools_to_openai(tools)
			if tool_choice is not None:
				openai_tool_choice = _tool_choice_to_openai(tool_choice)

		openai_temperature = temperature if temperature is not None else openai.omit
		openai_max_tokens = max_tokens if max_tokens is not None else openai.omit

		stream = await client.chat.completions.create(
			model=self.model,
			messages=openai_messages,
			stream=True,
			max_tokens=openai_max_tokens,
			temperature=openai_temperature,
			tool_choice=openai_tool_choice,
			tools=openai_tools,
		)
		async for chunk in stream:
			if not chunk.choices:
				continue
			delta = chunk.choices[0].delta
			text = delta.content
			if text:
				yield AssistantMessage(content=[TextContent(text=text)])


def _tools_to_openai(tools: list[Tool]) -> list[OpenAIChatCompletionToolParam]:
	"""convert SDK tools to openai tool params."""
	result: list[OpenAIChatCompletionToolParam] = []
	for t in tools:
		function_def: OpenAIChatCompletionFunctionDefinition = {
			"name": t.name,
			"description": t.description,
			"parameters": dict[str, object](t.parameters),
		}
		result.append(
			OpenAIChatCompletionToolParam(
				type="function",
				function=function_def,
			)
		)
	return result


def _tool_choice_to_openai(
	tool_choice: str,
) -> OpenAIChatCompletionToolChoiceOptionParam:
	"""convert SDK tool_choice to openai format."""
	if tool_choice == "auto":
		return "auto"
	if tool_choice == "none":
		return "none"
	if tool_choice == "required":
		return "required"
	# specific function name
	return {"type": "function", "function": {"name": tool_choice}}


def _try_parse_tool_arguments(raw: str) -> tuple[JSONObject, JSONObject | None]:
	try:
		parsed = json.loads(raw)
	except json.JSONDecodeError as e:
		return (
			{},
			{"arguments_parse_error": str(e), "raw_arguments": raw},
		)

	if not isinstance(parsed, dict):
		return (
			{},
			{
				"arguments_parse_error": "tool arguments were not a json object",
				"raw_arguments": raw,
			},
		)

	args: JSONObject = {}
	for key, value in parsed.items():
		if isinstance(key, str):
			args[key] = value
		else:
			args[str(key)] = value

	return (args, None)


def _messages_to_openai_chat_completions(
	messages: list[Message],
) -> list[OpenAIChatCompletionMessageParam]:
	"""convert SDK messages into OpenAI chat.completions message params."""
	openai_messages: list[OpenAIChatCompletionMessageParam] = []
	for message in messages:
		match message:
			case UserMessage():
				openai_messages.append(
					OpenAIChatCompletionUserMessageParam(
						role="user",
						content=message.text,
					)
				)
			case SystemMessage():
				openai_messages.append(
					OpenAIChatCompletionSystemMessageParam(
						role="system",
						content=message.text,
					)
				)
			case AssistantMessage():
				openai_message = OpenAIChatCompletionAssistantMessageParam(
					role="assistant",
					content=message.text,
				)
				if message.tool_calls:
					openai_message["tool_calls"] = [
						OpenAIChatCompletionFunctionToolCallParam(
							id=tool_call.id,
							type="function",
							function={
								"name": tool_call.name,
								"arguments": json.dumps(tool_call.arguments),
							},
						)
						for tool_call in message.tool_calls
					]
				openai_messages.append(openai_message)
			case ToolMessage():
				openai_messages.append(
					OpenAIChatCompletionToolMessageParam(
						role="tool",
						tool_call_id=message.tool_result.tool_call_id,
						content=message.tool_result.output,
					)
				)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")
	return openai_messages
