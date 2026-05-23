"""message-aware token estimation.

estimates token counts for SDK messages and threads. uses the
heuristic estimator from utils.tokens for text and data-based
estimation for attachments.

separated from utils/tokens.py because these functions need runtime
imports from nokodo_ai.messages, which is forbidden in utils/.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from .messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	SystemMessage,
	TextContent,
	ToolMessage,
	UserMessage,
)
from .threads import Thread
from .tool import ToolDefinition
from .utils.tokens import estimate_tokens


# type alias matching messages.py Message union members
type Message = UserMessage | AssistantMessage | ToolMessage | SystemMessage


def estimate_message_tokens(message: Message) -> int:
	"""estimate token count for a single SDK message.

	for assistant messages with real usage data from the provider,
	returns the reported output_tokens (the actual generated token
	count for that response). note: usage.input_tokens is cumulative
	(total context for that API call) and must NOT be used here.

	for user/tool/system messages and assistant messages without
	usage data, falls back to the text heuristic.
	"""
	# assistant messages: use output_tokens if available (actual generated
	# token count for this response).
	if isinstance(message, AssistantMessage):
		if message.usage and message.usage.output_tokens > 0:
			return message.usage.output_tokens
		# fall through to heuristic for assistant messages without usage
		total = _estimate_content_parts_tokens(message.content)
		# include tool call tokens (name + arguments)
		for tc in message.tool_calls:
			total += estimate_tokens(tc.name)
			args_text = json.dumps(tc.arguments) if tc.arguments else ""
			total += estimate_tokens(args_text)
		return total

	if isinstance(message, UserMessage):
		return _estimate_content_parts_tokens(message.content)

	if isinstance(message, ToolMessage):
		total = estimate_tokens(message.tool_output)
		# tool attachments (images, files) add cost
		for att in message.attachments:
			total += _estimate_attachment_tokens(att)
		return total

	if isinstance(message, SystemMessage):
		return _estimate_content_parts_tokens(message.content)

	# unknown message type - serialize as fallback
	return estimate_tokens(str(message))


def estimate_thread_tokens(thread: Thread) -> int:
	"""estimate total token count for all messages in a thread."""
	return sum(estimate_message_tokens(m) for m in thread.messages)


def estimate_tool_definitions_tokens(tools: Sequence[ToolDefinition]) -> int:
	"""estimate prompt tokens consumed by tool definition schemas."""
	total = 0
	for tool in tools:
		payload = tool.model_dump(mode="json")
		text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
		total += estimate_tokens(text)
	return total


# -- internals --


def _estimate_content_parts_tokens(parts: Sequence[object]) -> int:
	"""estimate tokens for a list of content parts."""
	total = 0
	for part in parts:
		if isinstance(part, TextContent):
			total += estimate_tokens(part.text)
		elif isinstance(part, (ImageContent, FileContent)):
			total += _estimate_attachment_tokens(part)
		else:
			# JsonContent, RefusalContent, etc. - serialize as fallback
			total += estimate_tokens(str(part))
	return total


def _estimate_attachment_tokens(
	att: ImageContent | FileContent,
) -> int:
	"""estimate tokens for an image or file attachment.

	both images and files are treated equally: estimate from the
	actual data payload when available. URLs are NOT cheap -- the
	provider loads the full content server-side, so we estimate
	from the URL length as a minimum (the true cost is the loaded
	content, but we cannot know that without fetching it).
	"""
	# prefer base64 data when available (most accurate)
	if att.base64:
		return estimate_tokens(att.base64)
	# URL references are loaded by the provider as full content.
	# we can't know the actual size without fetching, so estimate
	# from the URL length as a floor. callers that need accuracy
	# should run estimation on the final SDK thread after
	# attachment injection.
	if att.url:
		return estimate_tokens(att.url)
	return 10  # minimal placeholder for empty attachments
