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
from nokodo_ai.adapters.chat import BaseChatAdapter, ChatGenerationParams
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


class AnthropicMessagesAdapter(BaseAnthropicAdapter, BaseChatAdapter):
	"""adapter for anthropic's /v1/messages endpoint."""

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
				messages, model=model, tools=tools, params=params
			)
		return self._generate_once(messages, model=model, tools=tools, params=params)

	async def _generate_once(
		self,
		messages: list[Message],
		model: str,
		tools: list[Tool] | None,
		params: ChatGenerationParams,
	) -> AssistantMessage:
		system_text, anthropic_messages = _messages_to_anthropic(messages)
		system_text = _apply_response_model_to_system(
			system_text, params.response_model
		)

		anthropic_tools = _tools_to_anthropic(tools) if tools else anthropic.omit
		anthropic_tool_choice = anthropic.omit
		if tools and params.tool_choice is not None:
			anthropic_tool_choice = _tool_choice_to_anthropic(params.tool_choice)

		response = await self._client.messages.create(
			model=model,
			max_tokens=params.max_tokens if params.max_tokens is not None else 1024,
			messages=anthropic_messages,
			system=system_text if system_text else anthropic.omit,
			temperature=params.temperature
			if params.temperature is not None
			else anthropic.omit,
			top_p=params.top_p if params.top_p is not None else anthropic.omit,
			top_k=params.top_k if params.top_k is not None else anthropic.omit,
			stop_sequences=params.stop if params.stop else anthropic.omit,
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
				raw_args = json.dumps(block.input) if block.input else "{}"
				tool_calls.append(
					ToolCall(
						name=block.name,
						arguments=raw_args,
						metadata={"anthropic_tool_call_id": block.id},
					)
				)
				continue

		if params.response_model:
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
		model: str,
		tools: list[Tool] | None,
		params: ChatGenerationParams,
	) -> AsyncIterator[AssistantMessage]:
		system_text, anthropic_messages = _messages_to_anthropic(messages)
		system_text = _apply_response_model_to_system(
			system_text, params.response_model
		)

		anthropic_tools = _tools_to_anthropic(tools) if tools else anthropic.omit
		anthropic_tool_choice = anthropic.omit
		if tools and params.tool_choice is not None:
			anthropic_tool_choice = _tool_choice_to_anthropic(params.tool_choice)

		stream = await self._client.messages.create(
			model=model,
			max_tokens=params.max_tokens if params.max_tokens is not None else 1024,
			messages=anthropic_messages,
			system=system_text if system_text else anthropic.omit,
			temperature=params.temperature
			if params.temperature is not None
			else anthropic.omit,
			top_p=params.top_p if params.top_p is not None else anthropic.omit,
			top_k=params.top_k if params.top_k is not None else anthropic.omit,
			stop_sequences=params.stop if params.stop else anthropic.omit,
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
				raw_args = buf if buf.strip() else "{}"
				yield AssistantMessage(
					tool_calls=[
						ToolCall(
							name=tool_name,
							arguments=raw_args,
							metadata={"anthropic_tool_call_id": tool_id},
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
						tool_use_id = (
							(call.metadata or {}).get("anthropic_tool_call_id")
							if call.metadata
							else None
						)
						if not isinstance(tool_use_id, str) or tool_use_id == "":
							tool_use_id = call.id
						input_map: dict[str, object] = {}
						if isinstance(call.arguments, dict):
							input_map = dict[str, object](call.arguments)
						elif isinstance(call.arguments, str):
							try:
								parsed = (
									json.loads(call.arguments)
									if call.arguments.strip()
									else {}
								)
							except json.JSONDecodeError:
								parsed = {}
							if isinstance(parsed, dict):
								input_map = dict[str, object](parsed)
						blocks.append(
							{
								"type": "tool_use",
								"id": tool_use_id,
								"name": call.name,
								"input": input_map,
							}
						)
				if not blocks:
					result.append({"role": "assistant", "content": ""})
				elif len(blocks) == 1 and blocks[0]["type"] == "text":
					result.append({"role": "assistant", "content": blocks[0]["text"]})
				else:
					result.append({"role": "assistant", "content": blocks})
			case ToolMessage():
				tool_use_id_value = (
					message.metadata.get("anthropic_tool_call_id")
					if message.metadata
					else None
				)
				if not isinstance(tool_use_id_value, str) or tool_use_id_value == "":
					raise ValueError(
						"ToolMessage missing anthropic_tool_call_id in metadata"
					)
				result.append(
					{
						"role": "user",
						"content": [
							ToolResultBlockParam(
								type="tool_result",
								tool_use_id=tool_use_id_value,
								content=message.tool_output,
								is_error=message.is_error,
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
