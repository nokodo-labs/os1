"""openai responses adapter - /v1/responses endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

import openai

from ...messages import (
	PROVIDER_DATA_KEY,
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
from ...tool import ToolDefinition
from ...utils.validators import validate
from ..base.chat import BaseChatAdapter, ChatGenerationParams
from .base import BaseOpenAIAdapter
from .types import (
	OpenAIEasyInputMessageParam,
	OpenAIResponseFunctionCallOutput,
	OpenAIResponseFunctionToolCall,
	OpenAIResponseFunctionToolCallParam,
	OpenAIResponseFunctionToolParam,
	OpenAIResponseInputItemParam,
	OpenAIResponseInputParam,
	OpenAIResponsesModel,
	OpenAIResponseTextConfigParam,
	OpenAIResponseTextDeltaEvent,
	OpenAIResponseTextJSONSchemaConfigParam,
	OpenAIResponseToolChoice,
)


if TYPE_CHECKING:
	from nokodo_ai.messages import Message


def _provider_tool_call_metadata(
	*, provider: str, tool_call_id: str
) -> dict[str, object]:
	return {
		PROVIDER_DATA_KEY: {
			provider: {
				"tool_call_id": tool_call_id,
			}
		}
	}


def _get_provider_tool_call_id(
	*,
	metadata: dict[str, object] | None,
	provider: str,
) -> str | None:
	if not metadata:
		return None
	provider_data = metadata.get(PROVIDER_DATA_KEY)
	if not isinstance(provider_data, dict):
		return None
	provider_entry = provider_data.get(provider)
	if not isinstance(provider_entry, dict):
		return None
	tool_call_id = provider_entry.get("tool_call_id")
	if isinstance(tool_call_id, str) and tool_call_id != "":
		return tool_call_id
	return None


class OpenAIResponsesAdapter(BaseOpenAIAdapter, BaseChatAdapter):
	"""adapter for openai's /v1/responses endpoint.

	this is the newer responses API with built-in tool handling.
	"""

	type: Literal["openai.responses"] = "openai.responses"

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
		params = params or ChatGenerationParams()
		if stream:
			return self._generate_streaming(
				messages,
				model=model,
				tools=tools,
				params=params,
			)
		return self._generate_once(messages, model=model, tools=tools, params=params)

	async def _generate_once(
		self,
		messages: list[Message],
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AssistantMessage:
		"""generate a completion using /v1/responses."""

		response = await self._client.responses.create(
			model=validate(model, OpenAIResponsesModel),
			input=_messages_to_openai_responses_input(messages),
			max_output_tokens=params.max_tokens
			if params.max_tokens is not None
			else openai.omit,
			temperature=params.temperature
			if params.temperature is not None
			else openai.omit,
			text=OpenAIResponseTextConfigParam(
				format=OpenAIResponseTextJSONSchemaConfigParam(
					type="json_schema",
					name="response",
					strict=True,
					schema=dict[str, object](params.response_model),
				)
			)
			if params.response_model
			else openai.omit,
			tool_choice=_tool_choice_to_openai_responses(params.tool_choice)
			if params.tool_choice is not None
			else openai.omit,
			tools=_tools_to_openai_responses(tools) if tools else openai.omit,
			top_p=params.top_p if params.top_p is not None else openai.omit,
		)

		tool_calls: list[ToolCall] = []
		for item in response.output:
			if not isinstance(item, OpenAIResponseFunctionToolCall):
				continue
			tool_calls.append(
				ToolCall(
					name=item.name,
					arguments=item.arguments,
					metadata=_provider_tool_call_metadata(
						provider="openai.responses",
						tool_call_id=item.call_id,
					),
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
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AsyncIterator[AssistantMessage]:
		"""stream a completion using /v1/responses."""

		openai_tools = openai.omit
		openai_tool_choice = openai.omit
		if tools:
			openai_tools = _tools_to_openai_responses(tools)
			if params.tool_choice is not None:
				openai_tool_choice = _tool_choice_to_openai_responses(
					params.tool_choice
				)

		stream = await self._client.responses.create(
			model=validate(model, OpenAIResponsesModel),
			input=_messages_to_openai_responses_input(messages),
			stream=True,
			max_output_tokens=params.max_tokens
			if params.max_tokens is not None
			else openai.omit,
			temperature=params.temperature
			if params.temperature is not None
			else openai.omit,
			tool_choice=openai_tool_choice,
			tools=openai_tools,
			top_p=params.top_p if params.top_p is not None else openai.omit,
		)
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
						openai_tool_call_id = _get_provider_tool_call_id(
							metadata=tool_call.metadata,
							provider="openai.responses",
						)
						if openai_tool_call_id is None:
							raise ValueError(
								"ToolCall missing provider tool_call_id in metadata"
							)
						openai_messages.append(
							OpenAIResponseFunctionToolCallParam(
								type="function_call",
								call_id=openai_tool_call_id,
								name=tool_call.name,
								arguments=tool_call.arguments
								if isinstance(tool_call.arguments, str)
								else json.dumps(tool_call.arguments),
							)
						)
			case ToolMessage():
				openai_tool_call_id = _get_provider_tool_call_id(
					metadata=message.metadata,
					provider="openai.responses",
				)
				if openai_tool_call_id is None:
					raise ValueError(
						"ToolMessage missing provider tool_call_id in metadata"
					)
				openai_messages.append(
					OpenAIResponseFunctionCallOutput(
						type="function_call_output",
						call_id=openai_tool_call_id,
						output=message.tool_output,
					)
				)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")
	return openai_messages


def _tools_to_openai_responses(
	tools: list[ToolDefinition],
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
