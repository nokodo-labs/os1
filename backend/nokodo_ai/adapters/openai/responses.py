"""openai responses adapter - /v1/responses endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

import openai

from nokodo_ai.adapters.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.types import (
	OpenAIEasyInputMessageParam,
	OpenAIResponseFunctionCallOutput,
	OpenAIResponseFunctionToolCall,
	OpenAIResponseFunctionToolCallParam,
	OpenAIResponseFunctionToolParam,
	OpenAIResponseInputItemParam,
	OpenAIResponseInputParam,
	OpenAIResponseTextConfigParam,
	OpenAIResponseTextDeltaEvent,
	OpenAIResponseTextJSONSchemaConfigParam,
	OpenAIResponseToolChoice,
)
from nokodo_ai.message import (
	AssistantMessage,
	ContentPart,
	JsonContent,
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


class OpenAIResponsesAdapter(BaseOpenAIAdapter, BaseChatAdapter):
	"""adapter for openai's /v1/responses endpoint.

	this is the newer responses API with built-in tool handling.
	"""

	def __init__(
		self,
		*,
		model: str = "gpt-4o",
		api_key: str | None = None,
		base_url: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize responses adapter.

		args:
			model: model identifier
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
		stream: Literal[False] = False,
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		stream: Literal[True],
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		stream: bool = False,
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		params = params or ChatGenerationParams()
		if stream:
			return self._generate_streaming(messages, tools=tools, params=params)
		return self._generate_once(messages, tools=tools, params=params)

	async def _generate_once(
		self,
		messages: list[Message],
		*,
		tools: list[Tool] | None,
		params: ChatGenerationParams,
	) -> AssistantMessage:
		"""generate a completion using /v1/responses."""
		input_items = _messages_to_openai_responses_input(messages)

		openai_tools = openai.omit
		openai_tool_choice = openai.omit
		if tools:
			openai_tools = _tools_to_openai_responses(tools)
			if params.tool_choice is not None:
				openai_tool_choice = _tool_choice_to_openai_responses(
					params.tool_choice
				)

		text = openai.omit
		if params.response_model:
			text = OpenAIResponseTextConfigParam(
				format=OpenAIResponseTextJSONSchemaConfigParam(
					type="json_schema",
					name="response",
					strict=True,
					schema=dict[str, object](params.response_model),
				)
			)

		openai_temperature = (
			params.temperature if params.temperature is not None else openai.omit
		)
		openai_max_output_tokens = (
			params.max_tokens if params.max_tokens is not None else openai.omit
		)

		request_kwargs = {
			"model": self.model,
			"input": input_items,
			"max_output_tokens": openai_max_output_tokens,
			"temperature": openai_temperature,
			"text": text,
			"tool_choice": openai_tool_choice,
			"tools": openai_tools,
		}

		if params.top_p is not None:
			request_kwargs["top_p"] = params.top_p
		if params.stop:
			request_kwargs["stop"] = params.stop
		if params.seed is not None:
			request_kwargs["seed"] = params.seed
		if params.logit_bias is not None:
			request_kwargs["logit_bias"] = params.logit_bias
		if params.presence_penalty is not None:
			request_kwargs["presence_penalty"] = params.presence_penalty
		if params.frequency_penalty is not None:
			request_kwargs["frequency_penalty"] = params.frequency_penalty

		response = await self._client.responses.create(**request_kwargs)

		tool_calls: list[ToolCall] = []
		for item in response.output:
			if not isinstance(item, OpenAIResponseFunctionToolCall):
				continue
			args, metadata = _try_parse_tool_arguments(item.arguments)
			tool_calls.append(
				ToolCall(
					id=item.call_id,
					name=item.name,
					arguments=args,
					metadata=metadata,
				)
			)

		content: list[ContentPart] = []
		if params.response_model and response.output_text:
			try:
				content.append(JsonContent(data=json.loads(response.output_text)))
			except json.JSONDecodeError:
				content.append(TextContent(text=response.output_text))
		elif response.output_text:
			content.append(TextContent(text=response.output_text))

		usage: Usage | None = None
		if response.usage:
			usage = Usage(
				input_tokens=response.usage.input_tokens,
				output_tokens=response.usage.output_tokens,
				total_tokens=response.usage.total_tokens,
			)

		return AssistantMessage(content=content, tool_calls=tool_calls, usage=usage)

	async def _generate_streaming(
		self,
		messages: list[Message],
		*,
		tools: list[Tool] | None,
		params: ChatGenerationParams,
	) -> AsyncIterator[AssistantMessage]:
		"""stream a completion using /v1/responses."""
		input_items = _messages_to_openai_responses_input(messages)

		openai_tools = openai.omit
		openai_tool_choice = openai.omit
		if tools:
			openai_tools = _tools_to_openai_responses(tools)
			if params.tool_choice is not None:
				openai_tool_choice = _tool_choice_to_openai_responses(
					params.tool_choice
				)

		openai_temperature = (
			params.temperature if params.temperature is not None else openai.omit
		)
		openai_max_output_tokens = (
			params.max_tokens if params.max_tokens is not None else openai.omit
		)

		request_kwargs = {
			"model": self.model,
			"input": input_items,
			"stream": True,
			"max_output_tokens": openai_max_output_tokens,
			"temperature": openai_temperature,
			"tool_choice": openai_tool_choice,
			"tools": openai_tools,
		}

		if params.top_p is not None:
			request_kwargs["top_p"] = params.top_p
		if params.stop:
			request_kwargs["stop"] = params.stop
		if params.seed is not None:
			request_kwargs["seed"] = params.seed
		if params.logit_bias is not None:
			request_kwargs["logit_bias"] = params.logit_bias
		if params.presence_penalty is not None:
			request_kwargs["presence_penalty"] = params.presence_penalty
		if params.frequency_penalty is not None:
			request_kwargs["frequency_penalty"] = params.frequency_penalty

		stream = await self._client.responses.create(**request_kwargs)
		async for event in stream:
			if isinstance(event, OpenAIResponseTextDeltaEvent):
				if event.delta:
					yield AssistantMessage(content=[TextContent(text=event.delta)])


def _messages_to_openai_responses_input(
	messages: list[Message],
) -> OpenAIResponseInputParam:
	"""convert SDK messages into OpenAI Responses input items."""
	openai_messages: list[OpenAIResponseInputItemParam] = []
	for message in messages:
		match message:
			case UserMessage():
				openai_messages.append(
					OpenAIEasyInputMessageParam(
						type="message",
						role="user",
						content=message.text,
					)
				)
			case SystemMessage():
				openai_messages.append(
					OpenAIEasyInputMessageParam(
						type="message",
						role="system",
						content=message.text,
					)
				)
			case AssistantMessage():
				if message.text:
					openai_messages.append(
						OpenAIEasyInputMessageParam(
							type="message",
							role="assistant",
							content=message.text,
						)
					)
				if message.tool_calls:
					for tool_call in message.tool_calls:
						openai_messages.append(
							OpenAIResponseFunctionToolCallParam(
								type="function_call",
								call_id=tool_call.id,
								name=tool_call.name,
								arguments=json.dumps(tool_call.arguments),
							)
						)
			case ToolMessage():
				openai_messages.append(
					OpenAIResponseFunctionCallOutput(
						type="function_call_output",
						call_id=message.tool_result.tool_call_id,
						output=message.tool_result.output,
					)
				)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")
	return openai_messages


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


def _tools_to_openai_responses(
	tools: list[Tool],
) -> list[OpenAIResponseFunctionToolParam]:
	result: list[OpenAIResponseFunctionToolParam] = []
	for t in tools:
		result.append(
			{
				"type": "function",
				"name": t.name,
				"description": t.description,
				"strict": True,
				"parameters": dict[str, object](t.parameters),
			}
		)
	return result


def _tool_choice_to_openai_responses(tool_choice: str) -> OpenAIResponseToolChoice:
	if tool_choice in ("auto", "none", "required"):
		return tool_choice
	return {"type": "function", "name": tool_choice}
