"""openai chat completions adapter - /v1/chat/completions endpoint."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

import openai

from nokodo_ai.adapters.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.types import (
	OpenAIChatCompletion,
	OpenAIChatCompletionAssistantMessageParam,
	OpenAIChatCompletionFunctionDefinition,
	OpenAIChatCompletionFunctionToolCall,
	OpenAIChatCompletionFunctionToolCallParam,
	OpenAIChatCompletionMessageParam,
	OpenAIChatCompletionMessageToolCallUnion,
	OpenAIChatCompletionSystemMessageParam,
	OpenAIChatCompletionToolChoiceOptionParam,
	OpenAIChatCompletionToolMessageParam,
	OpenAIChatCompletionToolParam,
	OpenAIChatCompletionUserMessageParam,
	OpenAICompletionUsage,
	OpenAIJSONSchema,
	OpenAIResponseFormatJSONSchema,
)
from nokodo_ai.message import (
	AssistantMessage,
	ContentPart,
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

logger = logging.getLogger(__name__)


class OpenAIChatCompletionsAdapter(BaseOpenAIAdapter, BaseChatAdapter):
	"""adapter for openai's /v1/chat/completions endpoint.

	this is the standard openai chat API used by most applications.
	"""

	@overload
	def generate(
		self,
		messages: list[Message],
		stream: Literal[False] = False,
		model: str | None = None,
		tools: list[Tool] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		stream: Literal[True],
		model: str | None = None,
		tools: list[Tool] = [],
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		stream: bool = False,
		model: str | None = None,
		tools: list[Tool] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		params = params or ChatGenerationParams()
		if stream:
			return self._generate_streaming(messages, tools=tools, params=params)
		return self._generate_once(messages, tools=tools, params=params)

	async def _generate_once(
		self,
		messages: list[Message],
		model: str | None = None,
		tools: list[Tool] = [],
		params: ChatGenerationParams | None = None,
	) -> AssistantMessage:
		"""generate a completion using /v1/chat/completions."""

		response = await self._client.chat.completions.create(
			model=model,
			messages=_messages_to_openai_chat_completions(messages),
			tools=_tools_to_openai(tools) or openai.omit,
			tool_choice=_tool_choice_to_openai(params.tool_choice)
			if params and params.tool_choice is not None
			else openai.omit,
			max_tokens=params.max_tokens
			if params and params.max_tokens is not None
			else openai.omit,
			temperature=params.temperature
			if params and params.temperature is not None
			else openai.omit,
			response_format=_response_format_to_openai(params.response_model)  # type: ignore
			if params and params.response_model is not None
			else openai.omit,
			top_p=params.top_p if params and params.top_p is not None else openai.omit,
			stop=params.stop if params and params.stop else openai.omit,
			seed=params.seed if params and params.seed is not None else openai.omit,
			logit_bias=_logit_bias_to_openai(params.logit_bias)
			if params and params.logit_bias is not None
			else openai.omit,
			presence_penalty=params.presence_penalty
			if params and params.presence_penalty is not None
			else openai.omit,
			frequency_penalty=params.frequency_penalty
			if params and params.frequency_penalty is not None
			else openai.omit,
			reasoning_effort=params.reasoning_effort
			if params and params.reasoning_effort is not None
			else openai.omit,
		)

		return _chat_completion_to_assistant_message(response)

	async def _generate_streaming(
		self,
		messages: list[Message],
		model: str | None = None,
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]:
		"""stream a completion using /v1/chat/completions."""
		openai_messages = _messages_to_openai_chat_completions(messages)

		openai_tools = openai.omit
		openai_tool_choice = openai.omit
		if tools:
			openai_tools = _tools_to_openai(tools)
			if params.tool_choice is not None:
				openai_tool_choice = _tool_choice_to_openai(params.tool_choice)

		openai_temperature = (
			params.temperature if params.temperature is not None else openai.omit
		)
		openai_max_tokens = (
			params.max_tokens if params.max_tokens is not None else openai.omit
		)

		request_kwargs = {
			"model": model,
			"messages": openai_messages,
			"stream": True,
			"max_tokens": openai_max_tokens,
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
		if params.reasoning_effort is not None:
			request_kwargs["reasoning_effort"] = params.reasoning_effort

		stream = await self._client.chat.completions.create(**request_kwargs)
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


def _logit_bias_to_openai(
	logit_bias: dict[str, float],
) -> dict[str, int]:
	"""convert SDK logit bias to openai format (float to int)."""
	result: dict[str, int] = {}
	for key, value in logit_bias.items():
		result[key] = int(value)
	return result


def _response_format_to_openai(
	response_model: JSONObject,
) -> OpenAIResponseFormatJSONSchema:
	"""convert SDK response_model to openai response_format param."""
	return OpenAIResponseFormatJSONSchema(
		type="json_schema",
		json_schema=OpenAIJSONSchema(
			name="response",
			strict=True,
			schema=dict[str, object](response_model),
		),
	)


def _openai_usage_to_usage(openai_usage: OpenAICompletionUsage) -> Usage:
	"""convert openai CompletionUsage to SDK Usage."""
	return Usage(
		input_tokens=openai_usage.prompt_tokens,
		output_tokens=openai_usage.completion_tokens,
		total_tokens=openai_usage.total_tokens,
	)


def _openai_tool_calls_to_tool_calls(
	openai_tool_calls: list[OpenAIChatCompletionMessageToolCallUnion],
) -> list[ToolCall]:
	"""convert openai tool calls to SDK ToolCall."""
	tool_calls: list[ToolCall] = []
	for openai_tool_call in openai_tool_calls:
		if not isinstance(openai_tool_call, OpenAIChatCompletionFunctionToolCall):
			continue
		args = json.loads(openai_tool_call.function.arguments)
		metadata: JSONObject = {"openai_id": openai_tool_call.id}
		tool_calls.append(
			ToolCall(
				name=openai_tool_call.function.name,
				arguments=args,
				metadata=metadata,
			)
		)
	return tool_calls


def _chat_completion_to_assistant_message(
	completion: OpenAIChatCompletion,
) -> AssistantMessage:
	"""convert OpenAIChatCompletion to AssistantMessage."""
	if completion.usage is not None:
		usage = _openai_usage_to_usage(completion.usage)
	else:
		usage = None

	metadata: JSONObject = {}
	metadata["openai_id"] = completion.id

	content: list[ContentPart] = []
	tool_calls: list[ToolCall] = []
	finish_reason = "stop"
	if not completion.choices:
		pass
	else:
		for choice in completion.choices:
			openai_msg = choice.message
			tool_calls = _openai_tool_calls_to_tool_calls(openai_msg.tool_calls or [])

			if openai_msg.content is not None:
				content.append(TextContent(text=openai_msg.content))
			if choice.finish_reason == "content_filter":
				if openai_msg.refusal is None:
					logger.warning(
						"content filtered but no refusal reason provided by OpenAI"
					)
					refusal_reason = "content filtered"
				else:
					refusal_reason = openai_msg.refusal
				finish_reason = "content_filter"
				content.append(RefusalContent(reason=refusal_reason))
			elif choice.finish_reason in ("stop", "length", "tool_calls"):
				finish_reason = choice.finish_reason

	return AssistantMessage(
		content=content,
		tool_calls=tool_calls,
		usage=usage,
		finish_reason=finish_reason,
	)


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
