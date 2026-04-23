"""openai responses adapter - /v1/responses endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from time import time
from typing import TYPE_CHECKING, Literal, overload

import openai

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
from ...types import JSONObject
from ...utils.provider_meta import (
	RunIdTracker,
	get_provider_tool_call_id,
	get_provider_value,
	provider_tool_call_metadata,
)
from ...utils.validators import warn_known_model
from ..base.chat import BaseChatAdapter, ChatGenerationParams
from .base import BaseOpenAIAdapter
from .chat_completions import _to_openai_reasoning_effort
from .types import (
	OpenAIEasyInputMessageParam,
	OpenAIReasoning,
	OpenAIResponseCompletedEvent,
	OpenAIResponseCreatedEvent,
	OpenAIResponseFunctionCallArgumentsDeltaEvent,
	OpenAIResponseFunctionCallArgumentsDoneEvent,
	OpenAIResponseFunctionCallOutput,
	OpenAIResponseFunctionToolCall,
	OpenAIResponseFunctionToolCallParam,
	OpenAIResponseFunctionToolParam,
	OpenAIResponseInputContentParam,
	OpenAIResponseInputImageParam,
	OpenAIResponseInputItemParam,
	OpenAIResponseInputParam,
	OpenAIResponseInputTextParam,
	OpenAIResponseOutputItemAddedEvent,
	OpenAIResponsesModel,
	OpenAIResponseTextConfigParam,
	OpenAIResponseTextDeltaEvent,
	OpenAIResponseTextJSONSchemaConfigParam,
	OpenAIResponseToolChoice,
)


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
			model=warn_known_model(model, OpenAIResponsesModel),
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
			reasoning=OpenAIReasoning(
				effort=_to_openai_reasoning_effort(params.reasoning_effort)
			)
			if params.reasoning_effort is not None
			else openai.omit,
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
					metadata=provider_tool_call_metadata(
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

		openai_tools: list[OpenAIResponseFunctionToolParam] | openai.Omit = openai.omit
		openai_tool_choice: OpenAIResponseToolChoice | openai.Omit = openai.omit
		if tools:
			openai_tools = _tools_to_openai_responses(tools)
			if params.tool_choice is not None:
				openai_tool_choice = _tool_choice_to_openai_responses(
					params.tool_choice
				)

		stream = await self._client.responses.create(
			model=warn_known_model(model, OpenAIResponsesModel),
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
			reasoning=OpenAIReasoning(
				effort=_to_openai_reasoning_effort(params.reasoning_effort)
			)
			if params.reasoning_effort is not None
			else openai.omit,
			top_p=params.top_p if params.top_p is not None else openai.omit,
		)

		# transport: output_index → provider call_id
		idx_to_call_id: dict[int, str] = {}
		# canonical: provider call_id → SDK tool call id
		call_id_to_sdk_id: dict[str, str] = {}
		# provider call_id → state
		tc_created_at: dict[str, float] = {}
		tc_metadata: dict[str, JSONObject] = {}
		tc_names: dict[str, str] = {}

		run_tracker = RunIdTracker("openai.responses")

		async for event in stream:
			now = time()

			# --- response.created: surface the provider run id so the
			# cancel path can find it in metadata.
			if isinstance(event, OpenAIResponseCreatedEvent):
				meta_chunk = run_tracker.observe(event.response.id)
				if meta_chunk is not None:
					yield meta_chunk
				continue

			# --- text delta ---
			if isinstance(event, OpenAIResponseTextDeltaEvent):
				if event.delta:
					yield AssistantMessage(
						content=[TextContent(text=event.delta)],
						created_at=now,
						updated_at=now,
					)
				continue

			# --- tool call: output item added (first delta) ---
			if isinstance(event, OpenAIResponseOutputItemAddedEvent):
				item = event.item
				if isinstance(item, OpenAIResponseFunctionToolCall):
					call_id = item.call_id
					idx_to_call_id[event.output_index] = call_id
					tc_created_at[call_id] = now
					tc_names[call_id] = item.name
					tc_metadata[call_id] = provider_tool_call_metadata(
						provider="openai.responses",
						tool_call_id=call_id,
					)
					# create ToolCall with auto-generated SDK id
					tc = ToolCall(
						name=item.name,
						arguments="",
						created_at=now,
						updated_at=now,
						metadata=tc_metadata[call_id],
					)
					call_id_to_sdk_id[call_id] = tc.id
					yield AssistantMessage(
						tool_calls=[tc],
						created_at=now,
						updated_at=now,
					)
				continue

			# --- tool call: argument fragment ---
			if isinstance(event, OpenAIResponseFunctionCallArgumentsDeltaEvent):
				frag_call_id = idx_to_call_id.get(event.output_index)
				if frag_call_id and frag_call_id in call_id_to_sdk_id and event.delta:
					tc = ToolCall(
						id=call_id_to_sdk_id[frag_call_id],
						name=tc_names.get(frag_call_id, ""),
						arguments=event.delta,
						created_at=tc_created_at[frag_call_id],
						updated_at=now,
						metadata=tc_metadata.get(frag_call_id),
					)
					yield AssistantMessage(
						tool_calls=[tc],
						created_at=tc_created_at[frag_call_id],
						updated_at=now,
					)
				continue

			# --- tool call: arguments done (final name + full args for safety) ---
			if isinstance(event, OpenAIResponseFunctionCallArgumentsDoneEvent):
				# we already streamed all fragments; nothing extra to yield
				continue

			# --- response completed: extract usage ---
			if isinstance(event, OpenAIResponseCompletedEvent):
				response_usage = event.response.usage
				if response_usage:
					usage = Usage(
						input_tokens=response_usage.input_tokens,
						output_tokens=response_usage.output_tokens,
						total_tokens=response_usage.total_tokens,
					)
					yield AssistantMessage(usage=usage)

	async def cancel_generation(self, latest_message: AssistantMessage) -> bool:
		"""cancel an in-flight /v1/responses generation server-side.

		extracts the response id from the accumulated message's metadata,
		then calls ``POST /v1/responses/{id}/cancel``.

		:param latest_message: the accumulated ``AssistantMessage`` from
			streaming deltas.
		:returns: True if the provider acknowledged the cancel.
		"""
		run_id = get_provider_value(
			metadata=latest_message.metadata,
			provider="openai.responses",
			key="run_id",
		)
		if not isinstance(run_id, str) or not run_id:
			return False
		try:
			await self._client.responses.cancel(run_id)
		except Exception:
			return False
		return True


def _content_part_to_responses(
	part: ContentPart,
) -> OpenAIResponseInputContentParam | None:
	"""convert any SDK ContentPart to an openai responses input part.

	returns none for parts that have no representable content
	(empty text, images without data, etc).
	"""
	match part:
		case TextContent():
			if not part.text:
				return None
			return OpenAIResponseInputTextParam(
				type="input_text",
				text=part.text,
			)
		case JsonContent():
			if part.data is None:
				return None
			return OpenAIResponseInputTextParam(
				type="input_text",
				text=json.dumps(part.data),
			)
		case ImageContent():
			if part.base64 and part.media_type:
				return OpenAIResponseInputImageParam(
					type="input_image",
					image_url=(f"data:{part.media_type};base64,{part.base64}"),
					detail="auto",
				)
			if part.url:
				return OpenAIResponseInputImageParam(
					type="input_image",
					image_url=part.url,
					detail="auto",
				)
			return None
		case FileContent():
			if part.filename:
				return OpenAIResponseInputTextParam(
					type="input_text",
					text=f"[file: {part.filename}]",
				)
			return None
		case RefusalContent():
			if part.reason:
				return OpenAIResponseInputTextParam(
					type="input_text",
					text=f"[refused: {part.reason}]",
				)
			return None


def _content_parts_to_responses(
	parts: list[ContentPart],
) -> str | list[OpenAIResponseInputContentParam]:
	"""convert a list of SDK content parts to responses format.

	returns plain string when only text parts exist.
	returns typed content list when multimodal parts are present.
	"""
	has_non_text = any(not isinstance(p, TextContent) for p in parts)
	if not has_non_text:
		return "".join(p.text for p in parts if isinstance(p, TextContent))

	result: list[OpenAIResponseInputContentParam] = []
	for part in parts:
		converted = _content_part_to_responses(part)
		if converted is not None:
			result.append(converted)
	if not result:
		return "".join(p.text for p in parts if isinstance(p, TextContent))
	return result


def _tool_output_with_attachments(message: ToolMessage) -> str:
	"""build tool output string including attachment placeholders.

	Responses tool output only supports text. if the tool message
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


def _messages_to_openai_responses_input(
	messages: list[Message],
) -> OpenAIResponseInputParam:
	"""convert SDK messages into OpenAI Responses input items."""
	openai_messages: list[OpenAIResponseInputItemParam] = []
	for message in messages:
		match message:
			case UserMessage():
				content = _content_parts_to_responses(
					list(message.content),
				)
				openai_messages.append(
					OpenAIEasyInputMessageParam(
						type="message",
						role="user",
						content=content,
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
							get_provider_tool_call_id(
								metadata=tool_call.metadata,
								provider="openai.responses",
								fallback_id=tool_call.id,
							)
							or tool_call.id
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
				# Responses tool output only supports text -
				# append attachment placeholders
				openai_tool_call_id = (
					get_provider_tool_call_id(
						metadata=message.metadata,
						provider="openai.responses",
						fallback_id=message.tool_call_id,
					)
					or message.tool_call_id
				)
				openai_messages.append(
					OpenAIResponseFunctionCallOutput(
						type="function_call_output",
						call_id=openai_tool_call_id,
						output=_tool_output_with_attachments(
							message,
						),
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
	if tool_choice == "auto":
		return "auto"
	if tool_choice == "none":
		return "none"
	if tool_choice == "required":
		return "required"
	return {"type": "function", "name": tool_choice}
