"""google generate content adapter - google genai models.generate_content API."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Awaitable
from time import time
from typing import TYPE_CHECKING, Literal, overload

from google.genai.types import FunctionCallingConfigMode

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
from ...types.json import JSONValue
from ...utils.provider_meta import (
	get_provider_tool_call_id,
	get_provider_value,
	provider_tool_call_metadata,
)
from ..base.chat import BaseChatAdapter, ChatGenerationParams
from .base import BaseGoogleAdapter
from .types import (
	GoogleBlob,
	GoogleContent,
	GoogleFunctionCall,
	GoogleFunctionCallingConfig,
	GoogleFunctionDeclaration,
	GoogleGenerateContentConfig,
	GoogleGenerateContentResponse,
	GooglePart,
	GoogleThinkingConfig,
	GoogleThinkingLevel,
	GoogleTool,
	GoogleToolConfig,
	GoogleToolListUnion,
)


if TYPE_CHECKING:
	from nokodo_ai.messages import Message


PROVIDER_NAME = "google.generate_content"


_GOOGLE_THINKING_LEVEL: dict[str, GoogleThinkingLevel] = {
	"minimal": GoogleThinkingLevel.MINIMAL,
	"low": GoogleThinkingLevel.LOW,
	"medium": GoogleThinkingLevel.MEDIUM,
	"high": GoogleThinkingLevel.HIGH,
}


def _reasoning_effort_to_google(
	effort: str,
) -> GoogleThinkingConfig:
	"""convert reasoning_effort to a google ThinkingConfig."""
	if effort == "none":
		return GoogleThinkingConfig(thinking_budget=0)
	if effort == "max":
		return GoogleThinkingConfig(thinking_budget=-1)
	level = _GOOGLE_THINKING_LEVEL.get(effort, GoogleThinkingLevel.MEDIUM)
	return GoogleThinkingConfig(thinking_level=level)


def _tool_choice_to_google(tool_choice: str) -> GoogleToolConfig:
	"""convert SDK tool_choice to google format."""
	if tool_choice == "auto":
		mode = FunctionCallingConfigMode.AUTO
	elif tool_choice == "none":
		mode = FunctionCallingConfigMode.NONE
	elif tool_choice == "required":
		mode = FunctionCallingConfigMode.ANY
	else:
		# specific tool name - google supports allowed_function_names
		return GoogleToolConfig(
			function_calling_config=GoogleFunctionCallingConfig(
				mode=FunctionCallingConfigMode.ANY,
				allowed_function_names=[tool_choice],
			)
		)

	return GoogleToolConfig(
		function_calling_config=GoogleFunctionCallingConfig(mode=mode)
	)


def _tools_to_google(tools: list[ToolDefinition]) -> GoogleToolListUnion:
	"""convert SDK tools to google format."""
	function_declarations: list[GoogleFunctionDeclaration] = []
	for t in tools:
		function_declarations.append(
			GoogleFunctionDeclaration(
				name=t.name,
				description=t.description,
				parameters_json_schema=dict[str, object](t.parameters),
			)
		)
	return [GoogleTool(function_declarations=function_declarations)]


def _find_tool_name_from_history(
	messages: list[Message],
	tool_call_id: str,
) -> str | None:
	"""find the tool name from assistant message tool calls matching tool_call_id."""
	for msg in messages:
		if not isinstance(msg, AssistantMessage):
			continue
		for tc in msg.tool_calls:
			# check provider metadata first
			provider_id = get_provider_tool_call_id(
				metadata=tc.metadata, provider=PROVIDER_NAME
			)
			if provider_id == tool_call_id:
				return tc.name
			# fallback to tool call id
			if tc.id == tool_call_id:
				return tc.name
	return None


def _content_part_to_google(
	part: ContentPart,
) -> GooglePart | None:
	"""convert any SDK ContentPart to a google Part.

	returns none for parts that have no representable content
	(empty text, images without data, etc).
	"""
	match part:
		case TextContent():
			if not part.text:
				return None
			return GooglePart.from_text(text=part.text)
		case JsonContent():
			if part.data is None:
				return None
			return GooglePart.from_text(
				text=json.dumps(part.data),
			)
		case ImageContent():
			if part.base64 and part.media_type:
				return GooglePart(
					inline_data=GoogleBlob(
						data=base64.b64decode(part.base64),
						mime_type=part.media_type,
					)
				)
			if part.url:
				return GooglePart.from_uri(
					file_uri=part.url,
					mime_type=(part.media_type or "application/octet-stream"),
				)
			return None
		case FileContent():
			if part.filename:
				return GooglePart.from_text(
					text=f"[file: {part.filename}]",
				)
			return None
		case RefusalContent():
			if part.reason:
				return GooglePart.from_text(
					text=f"[refused: {part.reason}]",
				)
			return None


def _content_parts_to_google(
	parts: list[ContentPart],
) -> list[GooglePart]:
	"""convert a list of SDK content parts to google parts.

	always returns a list of GooglePart (google API requires parts list).
	falls back to empty text part if nothing converts.
	"""
	result: list[GooglePart] = []
	for part in parts:
		converted = _content_part_to_google(part)
		if converted is not None:
			result.append(converted)
	if not result:
		text = "".join(p.text for p in parts if isinstance(p, TextContent))
		return [GooglePart.from_text(text=text)]
	return result


def _tool_output_with_attachments(message: ToolMessage) -> str:
	"""build tool output string including attachment placeholders.

	google function_response is dict-only, no multimodal. if the tool
	message has attachments, append filename placeholders so the model
	knows they exist.
	"""
	if not message.attachments:
		return message.tool_output
	parts = [message.tool_output]
	for att in message.attachments:
		label = att.filename or "attachment"
		parts.append(f"[attached: {label}]")
	return "\n".join(parts)


def _messages_to_google(
	messages: list[Message],
) -> tuple[str | None, list[GoogleContent]]:
	"""convert SDK messages to google format."""
	system_parts: list[str] = []
	contents: list[GoogleContent] = []

	for message in messages:
		match message:
			case SystemMessage():
				if message.text:
					system_parts.append(message.text)
			case UserMessage():
				contents.append(
					GoogleContent(
						role="user",
						parts=_content_parts_to_google(
							list(message.content),
						),
					)
				)
			case AssistantMessage():
				parts: list[GooglePart] = _content_parts_to_google(
					list(message.content),
				)

				# add function calls as parts
				for tc in message.tool_calls:
					args_dict: dict[str, object] = {}
					if isinstance(tc.arguments, dict):
						args_dict = dict[str, object](tc.arguments)
					elif isinstance(tc.arguments, str):
						try:
							parsed = (
								json.loads(tc.arguments) if tc.arguments.strip() else {}
							)
						except json.JSONDecodeError:
							parsed = {}
						if isinstance(parsed, dict):
							args_dict = dict[str, object](parsed)

					# reconstruct Part with thought_signature if present
					thought_sig_b64 = get_provider_value(
						metadata=tc.metadata,
						provider=PROVIDER_NAME,
						key="thought_signature",
					)
					thought_val = get_provider_value(
						metadata=tc.metadata,
						provider=PROVIDER_NAME,
						key="thought",
					)
					if isinstance(thought_sig_b64, str):
						fc = GoogleFunctionCall(name=tc.name, args=args_dict)
						parts.append(
							GooglePart(
								function_call=fc,
								thought_signature=base64.b64decode(thought_sig_b64),
								thought=thought_val
								if isinstance(thought_val, bool)
								else None,
							)
						)
					else:
						parts.append(
							GooglePart.from_function_call(name=tc.name, args=args_dict)
						)

				if parts:
					contents.append(GoogleContent(role="model", parts=parts))
			case ToolMessage():
				# google requires function response with the function name
				# the name comes from the calling assistant message's tool call
				tool_name = _find_tool_name_from_history(messages, message.tool_call_id)
				if tool_name is None:
					# fallback: use tool_call_id as name (not ideal but won't crash)
					tool_name = message.tool_call_id

				# parse tool output as json if possible, otherwise wrap in result key
				# google function_response is dict-only, no multimodal -
				# include attachments as text
				output = _tool_output_with_attachments(message)
				try:
					response_dict = json.loads(output)
					if not isinstance(response_dict, dict):
						response_dict = {"result": response_dict}
				except json.JSONDecodeError:
					response_dict = {"result": output}

				contents.append(
					GoogleContent(
						role="user",
						parts=[
							GooglePart.from_function_response(
								name=tool_name,
								response=response_dict,
							)
						],
					)
				)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")

	system_text = "\n\n".join(system_parts) if system_parts else None
	return system_text, contents


def _response_to_assistant_message(
	response: GoogleGenerateContentResponse,
) -> AssistantMessage:
	"""convert google response to AssistantMessage."""
	tool_calls: list[ToolCall] = []
	content_parts: list[ContentPart] = []

	# extract text from response
	if response.text:
		content_parts.append(TextContent(text=response.text))

	# extract function calls from candidates
	for candidate_index, cand in enumerate(response.candidates or []):
		if cand.content is None:
			continue
		for part_index, part in enumerate(cand.content.parts or []):
			function_call = part.function_call
			if function_call is None:
				continue
			name = function_call.name
			if not name:
				continue
			args = function_call.args

			raw_args: str
			if isinstance(args, dict):
				raw_args = json.dumps(args)
			elif isinstance(args, str):
				raw_args = args
			else:
				raw_args = "{}"

			# create unique provider id for this tool call
			provider_id = f"c{candidate_index}_p{part_index}"
			extra: dict[str, JSONValue] = {}
			sig = getattr(part, "thought_signature", None)
			if isinstance(sig, bytes):
				extra["thought_signature"] = base64.b64encode(sig).decode("ascii")
			thought = getattr(part, "thought", None)
			if isinstance(thought, bool):
				extra["thought"] = thought
			tool_calls.append(
				ToolCall(
					name=name,
					arguments=raw_args,
					metadata=provider_tool_call_metadata(
						provider=PROVIDER_NAME,
						tool_call_id=provider_id,
						**extra,
					),
				)
			)

	# extract usage
	usage: Usage | None = None
	if response.usage_metadata is not None:
		prompt_tokens = response.usage_metadata.prompt_token_count
		output_tokens = response.usage_metadata.candidates_token_count
		total_tokens = response.usage_metadata.total_token_count
		if isinstance(prompt_tokens, int) and isinstance(output_tokens, int):
			total = (
				total_tokens
				if isinstance(total_tokens, int)
				else (prompt_tokens + output_tokens)
			)
			usage = Usage(
				input_tokens=prompt_tokens,
				output_tokens=output_tokens,
				total_tokens=total,
			)

	return AssistantMessage(content=content_parts, tool_calls=tool_calls, usage=usage)


class GoogleGenerateContentAdapter(BaseGoogleAdapter, BaseChatAdapter):
	"""adapter for google genai `models.generate_content` API."""

	type: Literal["google.generate_content"] = "google.generate_content"

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
				messages,
				model=model,
				tools=tools,
				params=params,
			)
		return self._generate_once(messages, model=model, tools=tools, params=params)

	async def cancel_generation(self, latest_message: AssistantMessage) -> bool:
		"""google genai does not expose per-request IDs or a cancel endpoint.

		closing the HTTP stream (which happens automatically when the
		asyncio task is cancelled) is the only way to stop generation.

		:param latest_message: unused - google has no cancel API.
		:returns: always False.
		"""
		return False

	async def _generate_once(
		self,
		messages: list[Message],
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AssistantMessage:
		system_text, contents = _messages_to_google(messages)

		google_tools = _tools_to_google(tools) if tools else None
		google_tool_config: GoogleToolConfig | None = None
		if tools and params.tool_choice is not None:
			google_tool_config = _tool_choice_to_google(params.tool_choice)

		config = GoogleGenerateContentConfig(
			temperature=params.temperature,
			top_p=params.top_p,
			top_k=params.top_k,
			max_output_tokens=params.max_tokens,
			system_instruction=system_text,
			tools=google_tools,
			tool_config=google_tool_config,
			stop_sequences=params.stop if params.stop else None,
			thinking_config=_reasoning_effort_to_google(params.reasoning_effort)
			if params.reasoning_effort is not None
			else None,
			response_mime_type="application/json" if params.response_model else None,
			response_json_schema=dict[str, object](params.response_model)
			if params.response_model
			else None,
		)

		response = await self._client.models.generate_content(
			model=model,
			contents=contents,
			config=config,
		)

		msg = _response_to_assistant_message(response)
		if params.response_model:
			text = "".join(p.text for p in msg.content if isinstance(p, TextContent))
			if text:
				try:
					parsed = json.loads(text)
					if isinstance(parsed, dict):
						non_text = [
							p for p in msg.content if not isinstance(p, TextContent)
						]
						msg = msg.model_copy(
							update={"content": [JsonContent(data=parsed)] + non_text}
						)
				except json.JSONDecodeError:
					pass
		return msg

	async def _generate_streaming(
		self,
		messages: list[Message],
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AsyncIterator[AssistantMessage]:
		system_text, contents = _messages_to_google(messages)

		google_tools = _tools_to_google(tools) if tools else None
		google_tool_config: GoogleToolConfig | None = None
		if tools and params.tool_choice is not None:
			google_tool_config = _tool_choice_to_google(params.tool_choice)

		config = GoogleGenerateContentConfig(
			temperature=params.temperature,
			top_p=params.top_p,
			top_k=params.top_k,
			max_output_tokens=params.max_tokens,
			system_instruction=system_text,
			tools=google_tools,
			tool_config=google_tool_config,
			stop_sequences=params.stop if params.stop else None,
			thinking_config=_reasoning_effort_to_google(params.reasoning_effort)
			if params.reasoning_effort is not None
			else None,
			response_mime_type="application/json" if params.response_model else None,
			response_json_schema=dict[str, object](params.response_model)
			if params.response_model
			else None,
		)

		stream = await self._client.models.generate_content_stream(
			model=model,
			contents=contents,
			config=config,
		)

		# per-provider_id state: auto-generated SDK id, name, created_at, metadata
		tc_sdk_ids: dict[str, str] = {}
		tc_created_at: dict[str, float] = {}
		final_usage: Usage | None = None

		async for chunk in stream:
			now = time()

			# extract usage from final chunk
			if chunk.usage_metadata is not None:
				prompt_tokens = chunk.usage_metadata.prompt_token_count
				output_tokens = chunk.usage_metadata.candidates_token_count
				total_tokens = chunk.usage_metadata.total_token_count
				if isinstance(prompt_tokens, int) and isinstance(output_tokens, int):
					total = (
						total_tokens
						if isinstance(total_tokens, int)
						else (prompt_tokens + output_tokens)
					)
					final_usage = Usage(
						input_tokens=prompt_tokens,
						output_tokens=output_tokens,
						total_tokens=total,
					)

			# --- text delta ---
			if chunk.text:
				yield AssistantMessage(
					content=[TextContent(text=chunk.text)],
					created_at=now,
					updated_at=now,
				)

			# --- tool call deltas ---
			for candidate_index, cand in enumerate(chunk.candidates or []):
				if cand.content is None:
					continue
				for part_index, part in enumerate(cand.content.parts or []):
					function_call = part.function_call
					if function_call is None:
						continue
					name = function_call.name
					if not name:
						continue
					args = function_call.args

					raw_args: str
					if isinstance(args, dict):
						raw_args = json.dumps(args)
					elif isinstance(args, str):
						raw_args = args
					else:
						raw_args = "{}"

					provider_id = f"c{candidate_index}_p{part_index}"
					extra_s: dict[str, JSONValue] = {}
					sig_s = getattr(part, "thought_signature", None)
					if isinstance(sig_s, bytes):
						extra_s["thought_signature"] = base64.b64encode(sig_s).decode(
							"ascii"
						)
					thought_s = getattr(part, "thought", None)
					if isinstance(thought_s, bool):
						extra_s["thought"] = thought_s
					metadata = provider_tool_call_metadata(
						provider=PROVIDER_NAME,
						tool_call_id=provider_id,
						**extra_s,
					)

					if provider_id not in tc_sdk_ids:
						# first delta for this tool call: auto-generate SDK id
						tc_created_at[provider_id] = now
						tc = ToolCall(
							name=name,
							arguments=raw_args,
							created_at=now,
							updated_at=now,
							metadata=metadata,
						)
						tc_sdk_ids[provider_id] = tc.id
						yield AssistantMessage(
							tool_calls=[tc],
							created_at=now,
							updated_at=now,
						)
					else:
						# subsequent delta: reuse SDK id
						tc = ToolCall(
							id=tc_sdk_ids[provider_id],
							name=name,
							arguments=raw_args,
							created_at=tc_created_at[provider_id],
							updated_at=now,
							metadata=metadata,
						)
						yield AssistantMessage(
							tool_calls=[tc],
							created_at=tc_created_at[provider_id],
							updated_at=now,
						)

		# emit usage at the end
		if final_usage is not None:
			yield AssistantMessage(usage=final_usage)
