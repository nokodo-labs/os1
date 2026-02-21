"""anthropic messages adapter - /v1/messages endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from time import time
from typing import TYPE_CHECKING, Literal, overload

import anthropic

from ...messages import (
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
from ...types import JSONObject
from ...utils.provider_meta import (
	get_provider_tool_call_id,
	provider_tool_call_metadata,
)
from ..base.chat import BaseChatAdapter, ChatGenerationParams
from .base import BaseAnthropicAdapter
from .types import (
	AnthropicInputJSONDelta,
	AnthropicMessageParam,
	AnthropicRawContentBlockDeltaEvent,
	AnthropicRawContentBlockStartEvent,
	AnthropicRawContentBlockStopEvent,
	AnthropicTextBlock,
	AnthropicTextBlockParam,
	AnthropicTextDelta,
	AnthropicToolChoiceAnyParam,
	AnthropicToolChoiceAutoParam,
	AnthropicToolChoiceNoneParam,
	AnthropicToolChoiceToolParam,
	AnthropicToolParam,
	AnthropicToolResultBlockParam,
	AnthropicToolUseBlock,
	AnthropicToolUseBlockParam,
)


if TYPE_CHECKING:
	from nokodo_ai.messages import Message


class AnthropicMessagesAdapter(BaseAnthropicAdapter, BaseChatAdapter):
	"""adapter for anthropic's /v1/messages endpoint."""

	type: Literal["anthropic.messages"] = "anthropic.messages"

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
				messages, model=model, tools=tools, params=params
			)
		return self._generate_once(messages, model=model, tools=tools, params=params)

	async def _generate_once(
		self,
		messages: list[Message],
		model: str,
		tools: list[ToolDefinition],
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
			if isinstance(block, AnthropicTextBlock):
				if block.text:
					content.append(TextContent(text=block.text))
				continue
			if isinstance(block, AnthropicToolUseBlock):
				raw_args = json.dumps(block.input) if block.input else "{}"
				tool_calls.append(
					ToolCall(
						name=block.name,
						arguments=raw_args,
						metadata=provider_tool_call_metadata(
							provider="anthropic.messages",
							tool_call_id=block.id,
						),
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
		tools: list[ToolDefinition],
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

		# transport: event index → provider tool call id
		idx_to_provider_id: dict[int, str] = {}
		# canonical: provider tool call id → SDK tool call id
		provider_to_sdk_id: dict[str, str] = {}
		# provider tool call id → state
		tc_names: dict[str, str] = {}
		tc_created_at: dict[str, float] = {}

		async for event in stream:
			now = time()

			if isinstance(event, AnthropicRawContentBlockStartEvent):
				block = event.content_block
				if isinstance(block, AnthropicToolUseBlock):
					provider_id = block.id
					idx_to_provider_id[event.index] = provider_id
					tc_created_at[provider_id] = now
					tc_names[provider_id] = block.name
					# create ToolCall with auto-generated SDK id
					tc = ToolCall(
						name=block.name,
						arguments="",
						created_at=now,
						updated_at=now,
						metadata=provider_tool_call_metadata(
							provider="anthropic.messages",
							tool_call_id=provider_id,
						),
					)
					provider_to_sdk_id[provider_id] = tc.id
					yield AssistantMessage(
						tool_calls=[tc],
						created_at=now,
						updated_at=now,
					)
				continue

			if isinstance(event, AnthropicRawContentBlockDeltaEvent):
				delta = event.delta
				if isinstance(delta, AnthropicTextDelta):
					if delta.text:
						yield AssistantMessage(
							content=[TextContent(text=delta.text)],
							created_at=now,
							updated_at=now,
						)
					continue
				if isinstance(delta, AnthropicInputJSONDelta):
					provider_id = idx_to_provider_id.get(event.index)
					if provider_id is None or provider_id not in provider_to_sdk_id:
						continue
					# yield the argument fragment as a delta
					if delta.partial_json:
						tc = ToolCall(
							id=provider_to_sdk_id[provider_id],
							name=tc_names.get(provider_id, ""),
							arguments=delta.partial_json,
							created_at=tc_created_at[provider_id],
							updated_at=now,
							metadata=provider_tool_call_metadata(
								provider="anthropic.messages",
								tool_call_id=provider_id,
							),
						)
						yield AssistantMessage(
							tool_calls=[tc],
							created_at=tc_created_at[provider_id],
							updated_at=now,
						)
					continue
				continue

			if isinstance(event, AnthropicRawContentBlockStopEvent):
				# all argument fragments already streamed; clean up transport
				provider_id = idx_to_provider_id.pop(event.index, None)
				if provider_id:
					tc_created_at.pop(provider_id, None)
					tc_names.pop(provider_id, None)
				continue


type AnthropicToolChoice = (
	AnthropicToolChoiceAutoParam
	| AnthropicToolChoiceAnyParam
	| AnthropicToolChoiceNoneParam
	| AnthropicToolChoiceToolParam
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
) -> tuple[str | None, list[AnthropicMessageParam]]:
	system_parts: list[str] = []
	result: list[AnthropicMessageParam] = []
	for message in messages:
		match message:
			case SystemMessage():
				if message.text:
					system_parts.append(message.text)
			case UserMessage():
				result.append({"role": "user", "content": message.text})
			case AssistantMessage():
				blocks: list[AnthropicTextBlockParam | AnthropicToolUseBlockParam] = []
				assistant_text = message.text
				if not assistant_text and message.json is not None:
					assistant_text = json.dumps(message.json)
				if assistant_text:
					blocks.append({"type": "text", "text": assistant_text})
				if message.tool_calls:
					for call in message.tool_calls:
						tool_use_id = (
							get_provider_tool_call_id(
								metadata=call.metadata,
								provider="anthropic.messages",
								fallback_id=call.id,
							)
							or call.id
						)
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
					get_provider_tool_call_id(
						metadata=message.metadata,
						provider="anthropic.messages",
						fallback_id=message.tool_call_id,
					)
					or message.tool_call_id
				)
				result.append(
					{
						"role": "user",
						"content": [
							AnthropicToolResultBlockParam(
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


def _tools_to_anthropic(tools: list[ToolDefinition]) -> list[AnthropicToolParam]:
	result: list[AnthropicToolParam] = []
	for t in tools:
		result.append(
			AnthropicToolParam(
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
		return AnthropicToolChoiceAutoParam(type="auto")
	if tool_choice == "none":
		return AnthropicToolChoiceNoneParam(type="none")
	if tool_choice == "required":
		return AnthropicToolChoiceAnyParam(type="any")
	return AnthropicToolChoiceToolParam(type="tool", name=tool_choice)
