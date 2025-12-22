"""anthropic messages adapter - /v1/messages endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

import anthropic
from anthropic.types.input_json_delta import InputJSONDelta
from anthropic.types.message_param import MessageParam
from anthropic.types.raw_content_block_delta_event import RawContentBlockDeltaEvent
from anthropic.types.raw_content_block_start_event import RawContentBlockStartEvent
from anthropic.types.raw_content_block_stop_event import RawContentBlockStopEvent
from anthropic.types.text_block import TextBlock
from anthropic.types.text_block_param import TextBlockParam
from anthropic.types.text_delta import TextDelta
from anthropic.types.tool_choice_any_param import ToolChoiceAnyParam
from anthropic.types.tool_choice_auto_param import ToolChoiceAutoParam
from anthropic.types.tool_choice_none_param import ToolChoiceNoneParam
from anthropic.types.tool_choice_tool_param import ToolChoiceToolParam
from anthropic.types.tool_param import ToolParam
from anthropic.types.tool_result_block_param import ToolResultBlockParam
from anthropic.types.tool_use_block import ToolUseBlock
from anthropic.types.tool_use_block_param import ToolUseBlockParam

from nokodo_ai.adapters.anthropic.base import BaseAnthropicAdapter
from nokodo_ai.adapters.chat import BaseChatAdapter
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
from nokodo_ai.types.json import JSONObject, JSONValue


if TYPE_CHECKING:
	from nokodo_ai.message import Message


class AnthropicMessagesAdapter(BaseAnthropicAdapter, BaseChatAdapter):
	"""adapter for anthropic's /v1/messages endpoint."""

	def __init__(
		self,
		*,
		model: str = "claude-sonnet-4-20250514",
		api_key: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize messages adapter.

		args:
			model: model identifier (e.g., "claude-sonnet-4-20250514")
			api_key: anthropic API key
			timeout: request timeout in seconds
		"""
		super().__init__(api_key=api_key, timeout=timeout)
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
		system_text, anthropic_messages = _messages_to_anthropic(messages)
		system_text = _apply_response_model_to_system(system_text, response_model)

		anthropic_tools = _tools_to_anthropic(tools) if tools else anthropic.omit
		anthropic_tool_choice = anthropic.omit
		if tools and tool_choice is not None:
			anthropic_tool_choice = _tool_choice_to_anthropic(tool_choice)

		anthropic_system = system_text if system_text else anthropic.omit
		anthropic_temperature = (
			temperature if temperature is not None else anthropic.omit
		)
		anthropic_max_tokens = max_tokens if max_tokens is not None else 1024

		response = await self.client.messages.create(
			model=self.model,
			max_tokens=anthropic_max_tokens,
			messages=anthropic_messages,
			system=anthropic_system,
			temperature=anthropic_temperature,
			tools=anthropic_tools,
			tool_choice=anthropic_tool_choice,
		)

		tool_calls: list[ToolCall] = []
		content: list[ContentPart] = []
		for block in response.content:
			if isinstance(block, TextBlock):
				if block.text:
					content.append(TextContent(text=block.text))
				continue
			if isinstance(block, ToolUseBlock):
				args, metadata = _coerce_tool_input(block.input)
				tool_calls.append(
					ToolCall(
						id=block.id,
						name=block.name,
						arguments=args,
						metadata=metadata,
					)
				)
				continue

		if response_model:
			combined_text = "".join(
				part.text for part in content if isinstance(part, TextContent)
			)
			if combined_text:
				try:
					parsed = json.loads(combined_text)
					if isinstance(parsed, dict):
						content = [JsonContent(data=parsed)]
					else:
						content = [TextContent(text=combined_text)]
				except json.JSONDecodeError:
					content = [TextContent(text=combined_text)]

		usage = Usage(
			input_tokens=response.usage.input_tokens,
			output_tokens=response.usage.output_tokens,
			total_tokens=response.usage.input_tokens + response.usage.output_tokens,
			cache_creation_input_tokens=response.usage.cache_creation_input_tokens,
			cache_read_input_tokens=response.usage.cache_read_input_tokens,
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
		system_text, anthropic_messages = _messages_to_anthropic(messages)
		system_text = _apply_response_model_to_system(system_text, response_model)

		anthropic_tools = _tools_to_anthropic(tools) if tools else anthropic.omit
		anthropic_tool_choice = anthropic.omit
		if tools and tool_choice is not None:
			anthropic_tool_choice = _tool_choice_to_anthropic(tool_choice)

		anthropic_system = system_text if system_text else anthropic.omit
		anthropic_temperature = (
			temperature if temperature is not None else anthropic.omit
		)
		anthropic_max_tokens = max_tokens if max_tokens is not None else 1024

		stream = await self.client.messages.create(
			model=self.model,
			max_tokens=anthropic_max_tokens,
			messages=anthropic_messages,
			system=anthropic_system,
			temperature=anthropic_temperature,
			tools=anthropic_tools,
			tool_choice=anthropic_tool_choice,
			stream=True,
		)

		tool_use_state: dict[int, tuple[str, str, str]] = {}
		# index -> (tool_id, tool_name, input_json_buffer)
		async for event in stream:
			if isinstance(event, RawContentBlockStartEvent):
				block = event.content_block
				if isinstance(block, ToolUseBlock):
					tool_use_state[event.index] = (block.id, block.name, "")
				continue

			if isinstance(event, RawContentBlockDeltaEvent):
				delta = event.delta
				if isinstance(delta, TextDelta):
					if delta.text:
						yield AssistantMessage(content=[TextContent(text=delta.text)])
					continue
				if isinstance(delta, InputJSONDelta):
					state = tool_use_state.get(event.index)
					if state is None:
						continue
					tool_id, tool_name, buf = state
					tool_use_state[event.index] = (
						tool_id,
						tool_name,
						buf + delta.partial_json,
					)
					continue
				continue

			if isinstance(event, RawContentBlockStopEvent):
				state = tool_use_state.get(event.index)
				if state is None:
					continue
				tool_id, tool_name, buf = state
				args, metadata = _try_parse_tool_input_json(buf)
				yield AssistantMessage(
					tool_calls=[
						ToolCall(
							id=tool_id,
							name=tool_name,
							arguments=args,
							metadata=metadata,
						)
					]
				)
				del tool_use_state[event.index]
				continue


type AnthropicToolChoice = (
	ToolChoiceAutoParam | ToolChoiceAnyParam | ToolChoiceNoneParam | ToolChoiceToolParam
)


def _apply_response_model_to_system(
	system_text: str | None,
	response_model: JSONObject | None,
) -> str | None:
	if response_model is None:
		return system_text

	schema_json = json.dumps(response_model)
	instruction = "return only valid json that matches this json schema: " + schema_json
	if system_text:
		return system_text + "\n\n" + instruction
	return instruction


def _messages_to_anthropic(
	messages: list[Message],
) -> tuple[str | None, list[MessageParam]]:
	system_parts: list[str] = []
	result: list[MessageParam] = []
	for message in messages:
		match message:
			case SystemMessage():
				if message.text:
					system_parts.append(message.text)
			case UserMessage():
				result.append({"role": "user", "content": message.text})
			case AssistantMessage():
				blocks: list[TextBlockParam | ToolUseBlockParam] = []
				assistant_text = message.text
				if not assistant_text and message.json is not None:
					assistant_text = json.dumps(message.json)
				if assistant_text:
					blocks.append({"type": "text", "text": assistant_text})
				if message.tool_calls:
					for call in message.tool_calls:
						blocks.append(
							{
								"type": "tool_use",
								"id": call.id,
								"name": call.name,
								"input": dict[str, object](call.arguments),
							}
						)
				if not blocks:
					result.append({"role": "assistant", "content": ""})
				elif len(blocks) == 1 and blocks[0]["type"] == "text":
					result.append({"role": "assistant", "content": blocks[0]["text"]})
				else:
					result.append({"role": "assistant", "content": blocks})
			case ToolMessage():
				result.append(
					{
						"role": "user",
						"content": [
							ToolResultBlockParam(
								type="tool_result",
								tool_use_id=message.tool_result.tool_call_id,
								content=message.tool_result.output,
								is_error=message.tool_result.is_error,
							)
						],
					}
				)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")

	system_text = "\n\n".join([t for t in system_parts if t.strip()])
	return (system_text or None, result)


def _tools_to_anthropic(tools: list[Tool]) -> list[ToolParam]:
	result: list[ToolParam] = []
	for t in tools:
		result.append(
			ToolParam(
				name=t.name,
				description=t.description,
				input_schema=dict[str, object](t.parameters),
			)
		)
	return result


def _tool_choice_to_anthropic(
	tool_choice: str,
) -> AnthropicToolChoice:
	if tool_choice == "auto":
		return ToolChoiceAutoParam(type="auto")
	if tool_choice == "none":
		return ToolChoiceNoneParam(type="none")
	if tool_choice == "required":
		return ToolChoiceAnyParam(type="any")
	return ToolChoiceToolParam(type="tool", name=tool_choice)


def _try_parse_tool_input_json(raw: str) -> tuple[JSONObject, JSONObject | None]:
	if raw.strip() == "":
		return ({}, None)

	try:
		parsed = json.loads(raw)
	except json.JSONDecodeError as e:
		return (
			{},
			{
				"arguments_parse_error": str(e),
				"raw_arguments": raw,
			},
		)

	if not isinstance(parsed, dict):
		return (
			{},
			{
				"arguments_parse_error": "tool input was not a json object",
				"raw_arguments": raw,
			},
		)

	input_map: dict[str, object] = {}
	for k, v in parsed.items():
		input_map[str(k)] = v

	return _coerce_tool_input(input_map)


def _coerce_tool_input(
	input_map: dict[str, object],
) -> tuple[JSONObject, JSONObject | None]:
	args: JSONObject = {}
	for key, value in input_map.items():
		ok, json_value = _coerce_json_value(value)
		if not ok:
			return (
				{},
				{
					"arguments_parse_error": "tool input contained non-json values",
					"raw_arguments": json.dumps(input_map, default=str),
				},
			)
		args[key] = json_value
	return (args, None)


def _coerce_json_value(value: object) -> tuple[bool, JSONValue]:
	if value is None:
		return (True, None)
	if isinstance(value, bool):
		return (True, value)
	if isinstance(value, int):
		return (True, value)
	if isinstance(value, float):
		return (True, value)
	if isinstance(value, str):
		return (True, value)
	if isinstance(value, list):
		out_list: list[JSONValue] = []
		for item in value:
			ok, coerced = _coerce_json_value(item)
			if not ok:
				return (False, None)
			out_list.append(coerced)
		return (True, out_list)
	if isinstance(value, dict):
		out_dict: dict[str, JSONValue] = {}
		for k, v in value.items():
			ok, coerced = _coerce_json_value(v)
			if not ok:
				return (False, None)
			out_dict[str(k)] = coerced
		return (True, out_dict)
	return (False, None)
