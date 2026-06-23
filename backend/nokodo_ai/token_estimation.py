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
from math import ceil

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
from .utils.tokens import CHARS_PER_TOKEN, estimate_tokens


# type alias matching messages.py Message union members
type Message = UserMessage | AssistantMessage | ToolMessage | SystemMessage


# interim native-media token heuristics. these intentionally avoid counting
# base64 length (a 780 KB image is ~1.06M base64 chars, which the text
# heuristic turns into ~266K bogus tokens). a follow-up measurement module
# will replace these rough constants with empirically derived numbers.
#
# images: vision models cost roughly a fixed band of tokens per image,
# largely independent of file size, so use a flat estimate.
_IMAGE_TOKENS = 1024
# time-based and document media scale with payload size; these divisors map
# raw decoded bytes to an approximate token cost per category.
_AUDIO_BYTES_PER_TOKEN = 320
_VIDEO_BYTES_PER_TOKEN = 1000
_PDF_BYTES_PER_TOKEN = 40
_DOC_BYTES_PER_TOKEN = 40
# fallbacks used when only a url is present (no bytes to size from).
_AUDIO_URL_TOKENS = 1500
_VIDEO_URL_TOKENS = 5000
_DOC_URL_TOKENS = 2000


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

	uses category-based heuristics rather than the base64/url string length,
	which massively overestimates native media. images use a flat per-image
	estimate; audio, video, and documents scale with the decoded payload
	size. url-only media (no bytes available) falls back to a category
	default. these are rough interim numbers pending real measurement.
	"""
	# images cost a roughly fixed band regardless of file size.
	if isinstance(att, ImageContent):
		return _IMAGE_TOKENS

	media = (att.media_type or "").lower()
	size = _attachment_byte_size(att)
	if media.startswith("audio/"):
		return _scaled(size, _AUDIO_BYTES_PER_TOKEN, _AUDIO_URL_TOKENS)
	if media.startswith("video/"):
		return _scaled(size, _VIDEO_BYTES_PER_TOKEN, _VIDEO_URL_TOKENS)
	if media == "application/pdf":
		return _scaled(size, _PDF_BYTES_PER_TOKEN, _DOC_URL_TOKENS)
	if media.startswith("text/"):
		# text documents map bytes ~ characters.
		return _scaled(size, CHARS_PER_TOKEN, _DOC_URL_TOKENS)
	return _scaled(size, _DOC_BYTES_PER_TOKEN, _DOC_URL_TOKENS)


def _attachment_byte_size(att: ImageContent | FileContent) -> int:
	"""decoded byte size of an attachment payload, 0 when only a url exists."""
	if att.base64:
		# base64 encodes 3 bytes per 4 chars.
		return (len(att.base64) * 3) // 4
	return 0


def _scaled(size: int, bytes_per_token: float, url_default: int) -> int:
	"""scale a byte size to tokens, or use a default when no bytes exist."""
	if size <= 0:
		return url_default
	return max(1, ceil(size / bytes_per_token))
