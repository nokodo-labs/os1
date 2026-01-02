"""openai chat completions adapter - /v1/chat/completions endpoint."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, cast, overload

import openai

from ...messages import (
	AssistantMessage,
	ContentPart,
	FinishReason,
	RefusalContent,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	Usage,
	UserMessage,
)
from ...tool import ToolDefinition
from ...types.json import JSONObject
from ...utils.validators import validate
from ..base.chat import BaseChatAdapter, ChatGenerationParams
from .base import BaseOpenAIAdapter
from .types import (
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
	OpenAIChatModel,
	OpenAICompletionUsage,
	OpenAIJSONSchema,
	OpenAIResponseFormatJSONSchema,
)


if TYPE_CHECKING:
	from nokodo_ai.messages import Message

logger = logging.getLogger(__name__)


class OpenAIChatCompletionsAdapter(BaseOpenAIAdapter, BaseChatAdapter):
	"""adapter for openai's /v1/chat/completions endpoint.

	this is the standard openai chat API used by most applications.
	"""

	type: Literal["openai.chat_completions"] = "openai.chat_completions"

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[False] = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[True],
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: bool = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		if tools is None:
			tools = []
		params = params or ChatGenerationParams()
		if stream:
			return self._generate_streaming(
				messages, model=model, tools=tools, params=params
			)
		return self._generate_once(messages, model=model, tools=tools, params=params)

	async def _generate_once(
		self,
		messages: list[Message],
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams | None = None,
	) -> AssistantMessage:
		"""generate a completion using /v1/chat/completions."""

		response = await self._client.chat.completions.create(
			model=validate(model, OpenAIChatModel),
			messages=_messages_to_openai_chatcompletions(messages),
			tools=_tools_to_openai_chatcompletions(tools) or openai.omit,
			tool_choice=_tool_choice_to_openai_chatcompletions(params.tool_choice)
			if params and params.tool_choice is not None
			else openai.omit,
			max_tokens=params.max_tokens
			if params and params.max_tokens is not None
			else openai.omit,
			temperature=params.temperature
			if params and params.temperature is not None
			else openai.omit,
			response_format=_response_format_to_openai_chatcompletions(
				params.response_model
			)
			if params and params.response_model is not None
			else openai.omit,
			top_p=params.top_p if params and params.top_p is not None else openai.omit,
			stop=params.stop if params and params.stop else openai.omit,
			seed=params.seed if params and params.seed is not None else openai.omit,
			logit_bias=_logit_bias_to_openai_chatcompletions(params.logit_bias)
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
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]:
		"""stream a completion using /v1/chat/completions."""
		params = params or ChatGenerationParams()

		stream = await self._client.chat.completions.create(
			model=validate(model, OpenAIChatModel),
			messages=_messages_to_openai_chatcompletions(messages),
			stream=True,
			tools=_tools_to_openai_chatcompletions(tools) or openai.omit,
			tool_choice=_tool_choice_to_openai_chatcompletions(params.tool_choice)
			if tools and params and params.tool_choice is not None
			else openai.omit,
			max_tokens=params.max_tokens
			if params and params.max_tokens is not None
			else openai.omit,
			temperature=params.temperature
			if params and params.temperature is not None
			else openai.omit,
			response_format=_response_format_to_openai_chatcompletions(
				params.response_model
			)
			if params and params.response_model is not None
			else openai.omit,
			top_p=params.top_p if params and params.top_p is not None else openai.omit,
			stop=params.stop if params and params.stop else openai.omit,
			seed=params.seed if params and params.seed is not None else openai.omit,
			logit_bias=_logit_bias_to_openai_chatcompletions(params.logit_bias)
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

		accumulated = _accumulate_streaming_chunks(stream)
		async for delta_message in accumulated:
			yield delta_message


def _tools_to_openai_chatcompletions(
	tools: list[ToolDefinition],
) -> list[OpenAIChatCompletionToolParam]:
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


def _tool_choice_to_openai_chatcompletions(
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


def _logit_bias_to_openai_chatcompletions(
	logit_bias: dict[str, float],
) -> dict[str, int]:
	"""convert SDK logit bias to openai format (float to int)."""
	result: dict[str, int] = {}
	for key, value in logit_bias.items():
		result[key] = int(value)
	return result


def _response_format_to_openai_chatcompletions(
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


async def _accumulate_streaming_chunks(stream) -> AsyncIterator[AssistantMessage]:
	"""process streaming chunks and yield delta messages, then final summary."""
	finish_reason: FinishReason | None = None
	usage: Usage | None = None
	refusal_parts: list[str] = []
	tool_call_ids: dict[int, str] = {}
	tool_call_names: dict[int, str] = {}
	tool_call_arguments: dict[int, str] = {}

	async for chunk in stream:
		if chunk.usage is not None:
			usage = _openai_usage_to_usage(chunk.usage)

		if not chunk.choices:
			continue

		for choice in chunk.choices:
			if choice.index != 0:
				continue

			if choice.finish_reason is not None:
				if choice.finish_reason in (
					"stop",
					"length",
					"tool_calls",
					"content_filter",
				):
					finish_reason = choice.finish_reason
				else:
					logger.warning("unknown openai finish reason")

			delta = choice.delta
			if delta.content:
				yield AssistantMessage(content=[TextContent(text=delta.content)])

			if delta.refusal:
				refusal_parts.append(delta.refusal)
				yield AssistantMessage(content=[RefusalContent(reason=delta.refusal)])

			if delta.tool_calls:
				for tool_call_delta in delta.tool_calls:
					index = tool_call_delta.index
					if tool_call_delta.id:
						tool_call_ids[index] = tool_call_delta.id
					if tool_call_delta.function and tool_call_delta.function.name:
						tool_call_names[index] = tool_call_delta.function.name
					if tool_call_delta.function and tool_call_delta.function.arguments:
						tool_call_arguments[index] = (
							tool_call_arguments.get(index, "")
							+ tool_call_delta.function.arguments
						)

	final_tool_calls = _build_tool_calls_from_deltas(
		tool_call_ids, tool_call_names, tool_call_arguments
	)

	final_content: list[ContentPart] = []
	refusal = "".join(refusal_parts)
	if finish_reason == "content_filter":
		final_content.append(RefusalContent(reason=refusal or "content filtered"))

	if finish_reason is not None or final_tool_calls or usage is not None:
		yield AssistantMessage(
			content=final_content,
			tool_calls=final_tool_calls,
			usage=usage,
			finish_reason=finish_reason,
		)


def _build_tool_calls_from_deltas(
	tool_call_ids: dict[int, str],
	tool_call_names: dict[int, str],
	tool_call_arguments: dict[int, str],
) -> list[ToolCall]:
	"""build final tool calls from accumulated streaming deltas."""
	final_tool_calls: list[ToolCall] = []
	for index in sorted(tool_call_names.keys() | tool_call_arguments.keys()):
		name = tool_call_names.get(index)
		if not name:
			logger.warning("openai tool call missing function name")
			continue

		openai_id = tool_call_ids.get(index)
		raw_args = tool_call_arguments.get(index) or "{}"
		metadata: JSONObject | None = None

		if openai_id is not None:
			if metadata is None:
				metadata = {}
			metadata["openai_tool_call_id"] = openai_id

		final_tool_calls.append(
			ToolCall(
				name=name,
				arguments=raw_args,
				metadata=metadata,
			)
		)
	return final_tool_calls


def _openai_tool_calls_to_tool_calls(
	openai_tool_calls: list[OpenAIChatCompletionMessageToolCallUnion],
) -> list[ToolCall]:
	"""convert openai tool calls to SDK ToolCall."""
	tool_calls: list[ToolCall] = []
	for openai_tool_call in openai_tool_calls:
		if not isinstance(openai_tool_call, OpenAIChatCompletionFunctionToolCall):
			continue
		raw_args = openai_tool_call.function.arguments or "{}"
		metadata: JSONObject = {"openai_tool_call_id": openai_tool_call.id}
		tool_calls.append(
			ToolCall(
				name=openai_tool_call.function.name,
				arguments=raw_args,
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


def _messages_to_openai_chatcompletions(
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
							id=cast(
								str,
								(tool_call.metadata or {}).get("openai_tool_call_id"),
							),
							type="function",
							function={
								"name": tool_call.name,
								"arguments": tool_call.arguments
								if isinstance(tool_call.arguments, str)
								else json.dumps(tool_call.arguments),
							},
						)
						for tool_call in message.tool_calls
					]
				openai_messages.append(openai_message)
			case ToolMessage():
				openai_tool_call_id = (
					message.metadata.get("openai_tool_call_id")
					if message.metadata
					else None
				)
				if openai_tool_call_id is None:
					raise ValueError(
						"ToolMessage missing openai_tool_call_id in metadata"
					)
				openai_messages.append(
					OpenAIChatCompletionToolMessageParam(
						role="tool",
						tool_call_id=cast(str, openai_tool_call_id),
						content=message.tool_output,
					)
				)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")
	return openai_messages
