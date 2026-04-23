"""openai chat completions adapter - /v1/chat/completions endpoint."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable
from time import time
from typing import TYPE_CHECKING, Literal, cast, overload

import openai

from ...messages import (
	AssistantMessage,
	ContentPart,
	FileContent,
	FinishReason,
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
from ...types import JSONObject
from ...utils.provider_meta import (
	RunIdTracker,
	get_provider_tool_call_id,
	provider_tool_call_metadata,
)
from ...utils.validators import warn_known_model
from ..base.chat import BaseChatAdapter, ChatGenerationParams
from .base import BaseOpenAIAdapter
from .types import (
	OpenAIAsyncStream,
	OpenAIChatCompletion,
	OpenAIChatCompletionAssistantMessageParam,
	OpenAIChatCompletionChunk,
	OpenAIChatCompletionContentPartImageParam,
	OpenAIChatCompletionContentPartParam,
	OpenAIChatCompletionContentPartTextParam,
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
	OpenAIReasoningEffort,
	OpenAIResponseFormatJSONSchema,
)


if TYPE_CHECKING:
	from nokodo_ai.messages import Message

logger = logging.getLogger(__name__)


def _to_openai_reasoning_effort(
	effort: Literal["none", "minimal", "low", "medium", "high", "max"],
) -> OpenAIReasoningEffort:
	"""map internal effort label to the openai API value ('max' -> 'xhigh')."""
	return "xhigh" if effort == "max" else effort


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
			model=warn_known_model(model, OpenAIChatModel),
			messages=_messages_to_openai_chatcompletions(messages),
			tools=_tools_to_openai_chatcompletions(tools) or openai.omit,
			tool_choice=_tool_choice_to_openai_chatcompletions(params.tool_choice)
			if tools and params and params.tool_choice is not None
			else openai.omit,
			max_completion_tokens=params.max_tokens
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
			reasoning_effort=_to_openai_reasoning_effort(params.reasoning_effort)
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
			model=warn_known_model(model, OpenAIChatModel),
			messages=_messages_to_openai_chatcompletions(messages),
			stream=True,
			tools=_tools_to_openai_chatcompletions(tools) or openai.omit,
			tool_choice=_tool_choice_to_openai_chatcompletions(params.tool_choice)
			if tools and params and params.tool_choice is not None
			else openai.omit,
			max_completion_tokens=params.max_tokens
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
			reasoning_effort=_to_openai_reasoning_effort(params.reasoning_effort)
			if params and params.reasoning_effort is not None
			else openai.omit,
		)

		async for delta_message in _openai_stream_to_assistant_messages(stream):
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
			strict=False,
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


async def _openai_stream_to_assistant_messages(
	stream: OpenAIAsyncStream[OpenAIChatCompletionChunk],
) -> AsyncIterator[AssistantMessage]:
	"""convert an openai streaming response into AssistantMessage deltas.

	yields one AssistantMessage per chunk - including tool call deltas.
	callers use AssistantMessage.merge() to accumulate into a final message.

	tool call IDs are auto-generated by the ToolCall model on first delta.
	the provider's tool call id is the canonical key for associating
	subsequent chunks to the correct SDK tool call.  a transport map
	(index → provider_id) handles chunks that lack the provider id.
	"""
	finish_reason: FinishReason | None = None
	usage: Usage | None = None
	refusal_parts: list[str] = []

	# transport: streaming index → provider tool call id
	idx_to_provider_id: dict[int, str] = {}
	# canonical: provider tool call id → SDK tool call id
	provider_to_sdk_id: dict[str, str] = {}
	# provider tool call id → state
	tc_names: dict[str, str] = {}
	tc_created_at: dict[str, float] = {}
	tc_metadata: dict[str, JSONObject] = {}

	run_tracker = RunIdTracker("openai.chat_completions")

	async for chunk in stream:
		now = time()

		chunk_id = getattr(chunk, "id", None)
		if chunk_id:
			meta_chunk = run_tracker.observe(chunk_id)
			if meta_chunk is not None:
				yield meta_chunk

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
					finish_reason = cast(FinishReason, choice.finish_reason)
				else:
					logger.warning("unknown openai finish reason")

			delta = choice.delta

			# --- text content ---
			if delta.content:
				yield AssistantMessage(
					content=[TextContent(text=delta.content)],
					created_at=now,
					updated_at=now,
				)

			# --- refusal content ---
			if delta.refusal:
				refusal_parts.append(delta.refusal)
				yield AssistantMessage(
					content=[RefusalContent(reason=delta.refusal)],
					created_at=now,
					updated_at=now,
				)

			# --- tool call deltas ---
			if delta.tool_calls:
				for tc_delta in delta.tool_calls:
					idx = tc_delta.index

					# resolve provider tool call id for this chunk
					if tc_delta.id:
						# provider id present: register the transport mapping
						idx_to_provider_id[idx] = tc_delta.id
					provider_id = idx_to_provider_id.get(idx)

					arg_fragment = ""
					if tc_delta.function and tc_delta.function.arguments:
						arg_fragment = tc_delta.function.arguments
					if tc_delta.function and tc_delta.function.name:
						name = tc_delta.function.name
						if provider_id:
							tc_names[provider_id] = name

					# first delta for this provider tool call
					if provider_id and provider_id not in provider_to_sdk_id:
						tc_created_at[provider_id] = now
						tc_metadata[provider_id] = provider_tool_call_metadata(
							provider="openai.chat_completions",
							tool_call_id=provider_id,
						)

						# create the ToolCall - auto-generates SDK id
						tc = ToolCall(
							name=tc_names.get(provider_id, ""),
							arguments=arg_fragment,
							created_at=now,
							updated_at=now,
							metadata=tc_metadata[provider_id],
						)
						provider_to_sdk_id[provider_id] = tc.id
						yield AssistantMessage(
							tool_calls=[tc],
							created_at=now,
							updated_at=now,
						)

					elif provider_id:
						# subsequent delta: reuse the SDK id
						tc = ToolCall(
							id=provider_to_sdk_id[provider_id],
							name=tc_names.get(provider_id, ""),
							arguments=arg_fragment,
							created_at=tc_created_at[provider_id],
							updated_at=now,
							metadata=tc_metadata[provider_id],
						)
						yield AssistantMessage(
							tool_calls=[tc],
							created_at=tc_created_at[provider_id],
							updated_at=now,
						)

	# --- final chunk: finish reason, usage, content filter refusal ---
	final_content: list[ContentPart] = []
	refusal = "".join(refusal_parts)
	if finish_reason == "content_filter":
		final_content.append(RefusalContent(reason=refusal or "content filtered"))

	if finish_reason is not None or usage is not None:
		yield AssistantMessage(
			content=final_content,
			usage=usage,
			finish_reason=finish_reason,
		)


def _openai_tool_calls_to_tool_calls(
	openai_tool_calls: list[OpenAIChatCompletionMessageToolCallUnion],
) -> list[ToolCall]:
	"""convert openai tool calls to SDK ToolCall."""
	tool_calls: list[ToolCall] = []
	for openai_tool_call in openai_tool_calls:
		if not isinstance(openai_tool_call, OpenAIChatCompletionFunctionToolCall):
			continue
		raw_args = openai_tool_call.function.arguments or "{}"
		metadata = provider_tool_call_metadata(
			provider="openai.chat_completions",
			tool_call_id=openai_tool_call.id,
		)
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
	finish_reason: FinishReason = "stop"
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
				finish_reason = cast(FinishReason, choice.finish_reason)
	return AssistantMessage(
		content=content,
		tool_calls=tool_calls,
		usage=usage,
		finish_reason=finish_reason,
	)


def _content_part_to_openai_cc(
	part: ContentPart,
) -> OpenAIChatCompletionContentPartParam | None:
	"""convert any SDK ContentPart to an openai chat.completions part.

	returns none for parts that have no representable content
	(empty text, images without data, etc).
	"""
	match part:
		case TextContent():
			if not part.text:
				return None
			return OpenAIChatCompletionContentPartTextParam(
				type="text",
				text=part.text,
			)
		case JsonContent():
			if part.data is None:
				return None
			return OpenAIChatCompletionContentPartTextParam(
				type="text",
				text=json.dumps(part.data),
			)
		case ImageContent():
			if part.base64 and part.media_type:
				return OpenAIChatCompletionContentPartImageParam(
					type="image_url",
					image_url={
						"url": (f"data:{part.media_type};base64,{part.base64}"),
						"detail": "auto",
					},
				)
			if part.url:
				return OpenAIChatCompletionContentPartImageParam(
					type="image_url",
					image_url={
						"url": part.url,
						"detail": "auto",
					},
				)
			return None
		case FileContent():
			if part.filename:
				return OpenAIChatCompletionContentPartTextParam(
					type="text",
					text=f"[file: {part.filename}]",
				)
			return None
		case RefusalContent():
			if part.reason:
				return OpenAIChatCompletionContentPartTextParam(
					type="text",
					text=f"[refused: {part.reason}]",
				)
			return None


def _content_parts_to_openai_cc(
	parts: list[ContentPart],
) -> str | list[OpenAIChatCompletionContentPartParam]:
	"""convert a list of SDK content parts to openai CC format.

	returns plain string when only text parts exist (cheaper).
	returns typed content list when multimodal parts are present.
	"""
	has_non_text = any(not isinstance(p, TextContent) for p in parts)
	if not has_non_text:
		return "".join(p.text for p in parts if isinstance(p, TextContent))

	result: list[OpenAIChatCompletionContentPartParam] = []
	for part in parts:
		converted = _content_part_to_openai_cc(part)
		if converted is not None:
			result.append(converted)
	if not result:
		return "".join(p.text for p in parts if isinstance(p, TextContent))
	return result


def _tool_output_with_attachments(message: ToolMessage) -> str:
	"""build tool output string including attachment placeholders.

	CC/Responses tool results only support text. if the tool message
	has attachments, append filename placeholders so the model
	knows they exist.
	"""
	if not message.attachments:
		return message.tool_output
	parts = [message.tool_output]
	for att in message.attachments:
		label = att.filename or "attachment"
		parts.append(f"[attached: {label}]")
	return "\n".join(parts)


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
						content=_content_parts_to_openai_cc(
							list(message.content),
						),
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
				# CC assistant messages only support text + refusal
				openai_message = OpenAIChatCompletionAssistantMessageParam(
					role="assistant",
					content=message.text or None,
				)
				if message.tool_calls:
					openai_message["tool_calls"] = [
						OpenAIChatCompletionFunctionToolCallParam(
							id=get_provider_tool_call_id(
								metadata=tool_call.metadata,
								provider="openai.chat_completions",
								fallback_id=tool_call.id,
							)
							or tool_call.id,
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
				# CC tool messages only support text -
				# append attachment placeholders so the model
				# knows they exist
				openai_tool_call_id = (
					get_provider_tool_call_id(
						metadata=message.metadata,
						provider="openai.chat_completions",
						fallback_id=message.tool_call_id,
					)
					or message.tool_call_id
				)
				content = _tool_output_with_attachments(
					message,
				)
				openai_messages.append(
					OpenAIChatCompletionToolMessageParam(
						role="tool",
						tool_call_id=openai_tool_call_id,
						content=content,
					)
				)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")
	return openai_messages
