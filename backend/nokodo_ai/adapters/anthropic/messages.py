"""anthropic messages adapter - /v1/messages endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from time import time
from typing import TYPE_CHECKING, Literal, TypeIs, overload

import anthropic

from ...messages import (
	AssistantMessage,
	ContentPart,
	FileContent,
	ImageContent,
	JsonContent,
	RefusalContent,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	Usage,
	UserMessage,
)
from ...tool import ToolDefinition
from ...utils.json_schema import process_schema
from ...utils.provider_meta import (
	RunIdTracker,
	get_provider_tool_call_id,
	provider_tool_call_metadata,
)
from ..base.chat import BaseChatAdapter, ChatGenerationParams
from .base import BaseAnthropicAdapter
from .exceptions import map_anthropic_generation_exceptions
from .types import (
	AnthropicBase64ImageSourceParam,
	AnthropicContentBlockParam,
	AnthropicImageBlockParam,
	AnthropicInputJSONDelta,
	AnthropicMessageParam,
	AnthropicRawContentBlockDeltaEvent,
	AnthropicRawContentBlockStartEvent,
	AnthropicRawContentBlockStopEvent,
	AnthropicRawMessageStartEvent,
	AnthropicTextBlock,
	AnthropicTextBlockParam,
	AnthropicTextDelta,
	AnthropicThinkingConfigParam,
	AnthropicToolChoice,
	AnthropicToolChoiceAnyParam,
	AnthropicToolChoiceAutoParam,
	AnthropicToolChoiceNoneParam,
	AnthropicToolChoiceToolParam,
	AnthropicToolParam,
	AnthropicToolResultBlockParam,
	AnthropicToolUseBlock,
	AnthropicToolUseBlockParam,
	AnthropicURLImageSourceParam,
)


if TYPE_CHECKING:
	from nokodo_ai.messages import Message


_ANTHROPIC_THINKING_BUDGET: dict[str, int] = {
	"minimal": 512,
	"low": 2000,
	"medium": 5000,
	"high": 10000,
}


def _reasoning_effort_to_anthropic(
	effort: str,
) -> AnthropicThinkingConfigParam:
	"""convert reasoning_effort to an anthropic thinking config param."""
	if effort == "none":
		return {"type": "disabled"}
	if effort == "max":
		return {"type": "adaptive"}
	budget = _ANTHROPIC_THINKING_BUDGET.get(effort, 5000)
	return {"type": "enabled", "budget_tokens": budget}


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

	async def cancel_generation(self, latest_message: AssistantMessage) -> bool:
		"""anthropic has no server-side cancel endpoint.

		closing the HTTP stream (which happens automatically when the
		asyncio task is cancelled) is the only way to stop generation.

		:param latest_message: unused - anthropic has no cancel API.
		:returns: always False.
		"""
		return False

	@map_anthropic_generation_exceptions
	async def _generate_once(
		self,
		messages: list[Message],
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AssistantMessage:
		system_text, anthropic_messages = _messages_to_anthropic(messages)

		anthropic_tools = _tools_to_anthropic(tools) if tools else anthropic.omit
		anthropic_tool_choice: AnthropicToolChoice | anthropic.Omit = anthropic.omit
		if tools and params.tool_choice is not None:
			anthropic_tool_choice = _tool_choice_to_anthropic(params.tool_choice)

		extra_headers: dict[str, str] | None = None
		extra_body: dict[str, object] | None = None
		if params.response_model is not None:
			extra_headers = {"anthropic-beta": "structured-outputs-2025-11-13"}
			processed = process_schema(
				dict(params.response_model),
				make_all_required=True,
				set_additionalproperties_field=True,
				process_defaults=False,
				process_examples=False,
				process_enums=False,
				process_array_constraints=True,
			)
			assert isinstance(processed, dict)
			extra_body = {
				"output_format": {
					"type": "json_schema",
					"schema": processed,
				}
			}

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
			thinking=_reasoning_effort_to_anthropic(params.reasoning_effort)
			if params.reasoning_effort is not None
			else anthropic.omit,
			tools=anthropic_tools,
			tool_choice=anthropic_tool_choice,
			extra_headers=extra_headers,
			extra_body=extra_body,
		)

		tool_calls: list[ToolCall] = []
		content: list[ContentPart] = []
		for block in response.content:
			if isinstance(block, AnthropicTextBlock):
				if block.text:
					if params.response_model:
						try:
							parsed = json.loads(block.text)
							if isinstance(parsed, dict):
								content.append(JsonContent(data=parsed))
							else:
								content.append(TextContent(text=block.text))
						except json.JSONDecodeError:
							content.append(TextContent(text=block.text))
					else:
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

		usage = Usage(
			input_tokens=response.usage.input_tokens,
			output_tokens=response.usage.output_tokens,
			total_tokens=response.usage.input_tokens + response.usage.output_tokens,
			cache_creation_input_tokens=response.usage.cache_creation_input_tokens,
			cache_read_input_tokens=response.usage.cache_read_input_tokens,
		)

		return AssistantMessage(content=content, tool_calls=tool_calls, usage=usage)

	@map_anthropic_generation_exceptions
	async def _generate_streaming(
		self,
		messages: list[Message],
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AsyncIterator[AssistantMessage]:
		system_text, anthropic_messages = _messages_to_anthropic(messages)

		anthropic_tools = _tools_to_anthropic(tools) if tools else anthropic.omit
		anthropic_tool_choice: AnthropicToolChoice | anthropic.Omit = anthropic.omit
		if tools and params.tool_choice is not None:
			anthropic_tool_choice = _tool_choice_to_anthropic(params.tool_choice)

		extra_headers: dict[str, str] | None = None
		extra_body: dict[str, object] | None = None
		if params.response_model is not None:
			extra_headers = {"anthropic-beta": "structured-outputs-2025-11-13"}
			processed = process_schema(
				dict(params.response_model),
				make_all_required=True,
				set_additionalproperties_field=True,
				process_defaults=False,
				process_examples=False,
				process_enums=False,
				process_array_constraints=True,
			)
			assert isinstance(processed, dict)
			extra_body = {
				"output_format": {
					"type": "json_schema",
					"schema": processed,
				}
			}

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
			thinking=_reasoning_effort_to_anthropic(params.reasoning_effort)
			if params.reasoning_effort is not None
			else anthropic.omit,
			tools=anthropic_tools,
			tool_choice=anthropic_tool_choice,
			extra_headers=extra_headers,
			extra_body=extra_body,
			stream=True,
		)

		# transport: event index → provider tool call id
		idx_to_provider_id: dict[int, str] = {}
		# canonical: provider tool call id → SDK tool call id
		provider_to_sdk_id: dict[str, str] = {}
		# provider tool call id → state
		tc_names: dict[str, str] = {}
		tc_created_at: dict[str, float] = {}

		run_tracker = RunIdTracker("anthropic.messages")

		async for event in stream:
			now = time()

			# --- message_start: surface the provider message id for
			# consistent metadata across all adapters.
			if isinstance(event, AnthropicRawMessageStartEvent):
				meta_chunk = run_tracker.observe(event.message.id)
				if meta_chunk is not None:
					yield meta_chunk
				continue

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
					frag_provider_id = idx_to_provider_id.get(event.index)
					if (
						frag_provider_id is None
						or frag_provider_id not in provider_to_sdk_id
					):
						continue
					# yield the argument fragment as a delta
					if delta.partial_json:
						tc = ToolCall(
							id=provider_to_sdk_id[frag_provider_id],
							name=tc_names.get(frag_provider_id, ""),
							arguments=delta.partial_json,
							created_at=tc_created_at[frag_provider_id],
							updated_at=now,
							metadata=provider_tool_call_metadata(
								provider="anthropic.messages",
								tool_call_id=frag_provider_id,
							),
						)
						yield AssistantMessage(
							tool_calls=[tc],
							created_at=tc_created_at[frag_provider_id],
							updated_at=now,
						)
					continue
				continue

			if isinstance(event, AnthropicRawContentBlockStopEvent):
				# all argument fragments already streamed; clean up transport
				stop_provider_id = idx_to_provider_id.pop(event.index, None)
				if stop_provider_id:
					tc_created_at.pop(stop_provider_id, None)
					tc_names.pop(stop_provider_id, None)
				continue


type _AnthropicMediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]

_ANTHROPIC_IMAGE_TYPES: tuple[_AnthropicMediaType, ...] = (
	"image/jpeg",
	"image/png",
	"image/gif",
	"image/webp",
)


def _is_anthropic_media_type(s: str) -> TypeIs[_AnthropicMediaType]:
	"""narrow a media type string to the supported anthropic image types."""
	return s in _ANTHROPIC_IMAGE_TYPES


def _content_part_to_anthropic(
	part: ContentPart,
) -> AnthropicTextBlockParam | AnthropicImageBlockParam | None:
	"""convert any SDK ContentPart to an anthropic content block.

	returns none for parts that have no representable content
	(empty text, images without data, etc).
	only returns text or image blocks - the two types valid in all
	anthropic content slots (user messages and tool results).
	"""
	match part:
		case TextContent():
			if not part.text:
				return None
			return AnthropicTextBlockParam(
				type="text",
				text=part.text,
			)
		case JsonContent():
			if part.data is None:
				return None
			return AnthropicTextBlockParam(
				type="text",
				text=json.dumps(part.data),
			)
		case ImageContent():
			if part.base64 and part.media_type:
				if not _is_anthropic_media_type(part.media_type):
					return None
				return AnthropicImageBlockParam(
					type="image",
					source=AnthropicBase64ImageSourceParam(
						type="base64",
						media_type=part.media_type,
						data=part.base64,
					),
				)
			if part.url and part.url.startswith("https://"):
				return AnthropicImageBlockParam(
					type="image",
					source=AnthropicURLImageSourceParam(
						type="url",
						url=part.url,
					),
				)
			return None
		case FileContent():
			if part.filename:
				return AnthropicTextBlockParam(
					type="text",
					text=f"[file: {part.filename}]",
				)
			return None
		case RefusalContent():
			if part.reason:
				return AnthropicTextBlockParam(
					type="text",
					text=f"[refused: {part.reason}]",
				)
			return None


def _content_parts_to_anthropic(
	parts: list[ContentPart],
) -> str | list[AnthropicContentBlockParam]:
	"""convert a list of SDK content parts to anthropic format.

	returns plain string when only text parts exist.
	returns typed content list when multimodal parts are present.
	"""
	has_non_text = any(not isinstance(p, TextContent) for p in parts)
	if not has_non_text:
		return "".join(p.text for p in parts if isinstance(p, TextContent))

	result: list[AnthropicContentBlockParam] = []
	for part in parts:
		converted = _content_part_to_anthropic(part)
		if converted is not None:
			result.append(converted)
	if not result:
		return "".join(p.text for p in parts if isinstance(p, TextContent))
	return result


def _tool_message_to_result_block(
	message: ToolMessage,
) -> AnthropicToolResultBlockParam:
	"""build a single tool_result block from a ToolMessage."""
	tool_use_id = (
		get_provider_tool_call_id(
			metadata=message.metadata,
			provider="anthropic.messages",
			fallback_id=message.tool_call_id,
		)
		or message.tool_call_id
	)

	tool_blocks: list[AnthropicTextBlockParam | AnthropicImageBlockParam] = []
	if message.tool_output:
		tool_blocks.append(
			AnthropicTextBlockParam(type="text", text=message.tool_output)
		)
	for att in message.attachments:
		block = _content_part_to_anthropic(att)
		if block is not None:
			tool_blocks.append(block)

	# collapse single text block to plain string
	tool_result: str | list[AnthropicTextBlockParam | AnthropicImageBlockParam]
	if (
		len(tool_blocks) == 1
		and isinstance(tool_blocks[0], dict)
		and tool_blocks[0].get("type") == "text"
	):
		tool_result = message.tool_output
	else:
		tool_result = tool_blocks if tool_blocks else message.tool_output

	return AnthropicToolResultBlockParam(
		type="tool_result",
		tool_use_id=tool_use_id,
		content=tool_result,
		is_error=message.is_error,
	)


def _append_anthropic_assistant_message(
	result: list[AnthropicMessageParam],
	assistant_text: str,
	tool_blocks: list[AnthropicToolUseBlockParam],
) -> None:
	"""append an assistant message while preserving anthropic's content shape."""
	blocks: list[AnthropicTextBlockParam | AnthropicToolUseBlockParam] = []
	if assistant_text:
		blocks.append({"type": "text", "text": assistant_text})
	blocks.extend(tool_blocks)

	if not blocks:
		return
	if len(blocks) == 1 and blocks[0]["type"] == "text":
		result.append(
			{
				"role": "assistant",
				"content": blocks[0]["text"],
			}
		)
		return
	result.append({"role": "assistant", "content": blocks})


def _messages_to_anthropic(
	messages: list[Message],
) -> tuple[str | None, list[AnthropicMessageParam]]:
	system_parts: list[str] = []
	result: list[AnthropicMessageParam] = []
	i = 0
	while i < len(messages):
		message = messages[i]
		match message:
			case SystemMessage():
				if message.text:
					system_parts.append(message.text)
				i += 1
			case UserMessage():
				content = _content_parts_to_anthropic(
					list(message.content),
				)
				result.append({"role": "user", "content": content})
				i += 1
			case AssistantMessage():
				assistant_text = message.text
				if not assistant_text and message.json_content is not None:
					assistant_text = json.dumps(message.json_content)
				tool_blocks: list[AnthropicToolUseBlockParam] = []
				tool_use_by_id: dict[str, AnthropicToolUseBlockParam] = {}
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
					tool_block: AnthropicToolUseBlockParam = {
						"type": "tool_use",
						"id": tool_use_id,
						"name": call.name,
						"input": input_map,
					}
					tool_blocks.append(tool_block)
					tool_use_by_id[tool_use_id] = tool_block

				if not tool_blocks:
					_append_anthropic_assistant_message(
						result,
						assistant_text=assistant_text,
						tool_blocks=[],
					)
					i += 1
					continue

				result_blocks: list[AnthropicToolResultBlockParam] = []
				matched_tool_ids: list[str] = []
				j = i + 1
				while j < len(messages) and isinstance(messages[j], ToolMessage):
					tm = messages[j]
					assert isinstance(tm, ToolMessage)
					result_block = _tool_message_to_result_block(tm)
					tool_use_id = result_block["tool_use_id"]
					if tool_use_id in tool_use_by_id:
						result_blocks.append(result_block)
						if tool_use_id not in matched_tool_ids:
							matched_tool_ids.append(tool_use_id)
					j += 1

				had_tool_messages = j > i + 1

				if matched_tool_ids:
					# some tool results matched - include matched tool_use
					# blocks plus synthetic error results for any unmatched
					unmatched_ids = [
						tid for tid in tool_use_by_id if tid not in matched_tool_ids
					]
					for uid in unmatched_ids:
						result_blocks.append(
							AnthropicToolResultBlockParam(
								type="tool_result",
								tool_use_id=uid,
								content=(
									"tool execution was interrupted or never completed"
								),
								is_error=True,
							)
						)
					_append_anthropic_assistant_message(
						result,
						assistant_text=assistant_text,
						tool_blocks=tool_blocks,
					)
					result.append({"role": "user", "content": result_blocks})
					i = j
					continue

				if had_tool_messages:
					# tool messages followed but none matched (corrupt data) -
					# strip tool_use blocks and skip past the lookahead
					_append_anthropic_assistant_message(
						result,
						assistant_text=assistant_text,
						tool_blocks=[],
					)
					i = j
				else:
					# no tool messages followed at all (interrupted run) -
					# keep tool_use blocks with synthetic error results so
					# anthropic receives a valid tool_use / tool_result pair
					for tid in tool_use_by_id:
						result_blocks.append(
							AnthropicToolResultBlockParam(
								type="tool_result",
								tool_use_id=tid,
								content=(
									"tool execution was interrupted or never completed"
								),
								is_error=True,
							)
						)
					_append_anthropic_assistant_message(
						result,
						assistant_text=assistant_text,
						tool_blocks=tool_blocks,
					)
					result.append({"role": "user", "content": result_blocks})
					i += 1
			case ToolMessage():
				# skip orphaned tool results. anthropic requires tool_result
				# blocks to immediately follow the assistant tool_use turn.
				i += 1
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
