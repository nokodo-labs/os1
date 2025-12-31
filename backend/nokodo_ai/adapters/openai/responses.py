"""openai responses adapter - /v1/responses endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

import openai

from nokodo_ai.adapters.base.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.types import (
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
from nokodo_ai.messages import (
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
from nokodo_ai.utils.validators import validate


if TYPE_CHECKING:
	from nokodo_ai.messages import Message


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
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[True],
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: bool = False,
		tools: list[Tool] | None = None,
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
		tools: list[Tool] | None,
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
					metadata={"openai_tool_call_id": item.call_id},
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
		tools: list[Tool] | None,
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
						openai_tool_call_id = (
							(tool_call.metadata or {}).get("openai_tool_call_id")
							if tool_call.metadata
							else None
						)
						if (
							not isinstance(openai_tool_call_id, str)
							or openai_tool_call_id == ""
						):
							raise ValueError(
								"ToolCall missing openai_tool_call_id in metadata"
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
				openai_tool_call_id = (
					message.metadata.get("openai_tool_call_id")
					if message.metadata
					else None
				)
				if (
					not isinstance(openai_tool_call_id, str)
					or openai_tool_call_id == ""
				):
					raise ValueError(
						"ToolMessage missing openai_tool_call_id in metadata"
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
