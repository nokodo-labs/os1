"""google generate content adapter - google genai models.generate_content API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from time import time
from typing import TYPE_CHECKING, Literal, overload

from google.genai.types import FunctionCallingConfigMode

from ...messages import (
	AssistantMessage,
	ContentPart,
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
from .base import BaseGoogleAdapter
from .types import (
	GoogleContent,
	GoogleFunctionCallingConfig,
	GoogleFunctionDeclaration,
	GoogleGenerateContentConfig,
	GoogleGenerateContentResponse,
	GooglePart,
	GoogleTool,
	GoogleToolConfig,
)


if TYPE_CHECKING:
	from nokodo_ai.messages import Message


PROVIDER_NAME = "google.generate_content"


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


def _tools_to_google(tools: list[ToolDefinition]) -> list[GoogleTool]:
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
						parts=[GooglePart.from_text(text=message.text)],
					)
				)
			case AssistantMessage():
				parts: list[GooglePart] = []

				# add text content
				assistant_text = message.text
				if not assistant_text and message.json is not None:
					assistant_text = json.dumps(message.json)
				if assistant_text:
					parts.append(GooglePart.from_text(text=assistant_text))

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
				try:
					response_dict = json.loads(message.tool_output)
					if not isinstance(response_dict, dict):
						response_dict = {"result": response_dict}
				except json.JSONDecodeError:
					response_dict = {"result": message.tool_output}

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
			tool_calls.append(
				ToolCall(
					name=name,
					arguments=raw_args,
					metadata=provider_tool_call_metadata(
						provider=PROVIDER_NAME, tool_call_id=provider_id
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

	async def _generate_once(
		self,
		messages: list[Message],
		*,
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AssistantMessage:
		system_text, contents = _messages_to_google(messages)
		system_text = _apply_response_model_to_system(
			system_text, params.response_model
		)

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
		)

		response = await self._client.models.generate_content(
			model=model,
			contents=contents,
			config=config,
		)

		return _response_to_assistant_message(response)

	async def _generate_streaming(
		self,
		messages: list[Message],
		*,
		model: str,
		tools: list[ToolDefinition],
		params: ChatGenerationParams,
	) -> AsyncIterator[AssistantMessage]:
		system_text, contents = _messages_to_google(messages)
		system_text = _apply_response_model_to_system(
			system_text, params.response_model
		)

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
					metadata = provider_tool_call_metadata(
						provider=PROVIDER_NAME,
						tool_call_id=provider_id,
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
