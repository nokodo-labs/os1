"""tests for token estimation and context budget utilities."""

from math import ceil

from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	Usage,
	UserMessage,
)
from nokodo_ai.threads import Thread
from nokodo_ai.token_estimation import (
	estimate_message_tokens,
	estimate_thread_tokens,
)
from nokodo_ai.utils.tokens import (
	CHARS_PER_TOKEN,
	DEFAULT_CONTEXT_WINDOW,
	DEFAULT_RESPONSE_HEADROOM,
	SAFETY_MARGIN,
	compute_available_budget,
	estimate_tokens,
)


# -- estimate_tokens --


class TestEstimateTokens:
	def test_empty_string(self) -> None:
		assert estimate_tokens("") == 0

	def test_short_text(self) -> None:
		text = "hello"
		expected = ceil(len(text) / CHARS_PER_TOKEN * SAFETY_MARGIN)
		assert estimate_tokens(text) == expected

	def test_long_text(self) -> None:
		text = "a" * 10_000
		expected = ceil(10_000 / CHARS_PER_TOKEN * SAFETY_MARGIN)
		assert estimate_tokens(text) == expected

	def test_safety_margin_inflates(self) -> None:
		# without margin: 400 chars / 4 = 100 tokens
		# with margin: 100 * 1.2 = 120 tokens
		text = "x" * 400
		raw = len(text) / CHARS_PER_TOKEN
		result = estimate_tokens(text)
		assert result > raw
		assert result == ceil(raw * SAFETY_MARGIN)


# -- estimate_message_tokens --


class TestEstimateMessageTokens:
	def test_user_message_text(self) -> None:
		msg = UserMessage.from_text("hello world")
		result = estimate_message_tokens(msg)
		assert result == estimate_tokens("hello world")

	def test_user_message_with_image(self) -> None:
		msg = UserMessage(
			content=[
				TextContent(text="check this"),
				ImageContent(url="https://example.com/img.png"),
			]
		)
		result = estimate_message_tokens(msg)
		# image urls are provider-loaded native media, not cheap URL text.
		image_tokens = 1024
		assert result == estimate_tokens("check this") + image_tokens

	def test_user_message_with_image_base64_uses_media_estimate(self) -> None:
		msg = UserMessage(
			content=[ImageContent(base64="x" * 40_000, media_type="image/png")]
		)
		result = estimate_message_tokens(msg)
		assert result == 1024
		assert result < estimate_tokens("x" * 40_000)

	def test_audio_attachment_scales_with_bytes(self) -> None:
		# base64 of 32_000 chars -> 24_000 decoded bytes -> bytes / 320.
		msg = ToolMessage(
			tool_call_id="tc_1",
			tool_output="",
			attachments=[FileContent(base64="x" * 32_000, media_type="audio/mpeg")],
		)
		result = estimate_message_tokens(msg)
		assert result == ceil((32_000 * 3 // 4) / 320)
		assert result < estimate_tokens("x" * 32_000)

	def test_video_attachment_scales_with_bytes(self) -> None:
		msg = ToolMessage(
			tool_call_id="tc_1",
			tool_output="",
			attachments=[FileContent(base64="x" * 40_000, media_type="video/mp4")],
		)
		result = estimate_message_tokens(msg)
		assert result == ceil((40_000 * 3 // 4) / 1000)

	def test_pdf_attachment_scales_with_bytes(self) -> None:
		msg = ToolMessage(
			tool_call_id="tc_1",
			tool_output="",
			attachments=[FileContent(base64="x" * 4_000, media_type="application/pdf")],
		)
		result = estimate_message_tokens(msg)
		assert result == ceil((4_000 * 3 // 4) / 40)

	def test_text_document_maps_bytes_to_chars(self) -> None:
		msg = ToolMessage(
			tool_call_id="tc_1",
			tool_output="",
			attachments=[FileContent(base64="x" * 4_000, media_type="text/plain")],
		)
		result = estimate_message_tokens(msg)
		assert result == ceil((4_000 * 3 // 4) / CHARS_PER_TOKEN)

	def test_unknown_document_uses_doc_divisor(self) -> None:
		msg = ToolMessage(
			tool_call_id="tc_1",
			tool_output="",
			attachments=[
				FileContent(
					base64="x" * 4_000,
					media_type="application/octet-stream",
				)
			],
		)
		result = estimate_message_tokens(msg)
		assert result == ceil((4_000 * 3 // 4) / 40)

	def test_url_only_file_uses_category_default(self) -> None:
		msg = ToolMessage(
			tool_call_id="tc_1",
			tool_output="",
			attachments=[
				FileContent(
					url="https://example.com/clip.mp4",
					media_type="video/mp4",
				)
			],
		)
		result = estimate_message_tokens(msg)
		assert result == 5000

	def test_assistant_message_with_usage(self) -> None:
		"""assistant messages with real output_tokens should use it."""
		msg = AssistantMessage.from_text("response text")
		msg.usage = Usage(input_tokens=500, output_tokens=100, total_tokens=600)
		result = estimate_message_tokens(msg)
		assert result == 100

	def test_assistant_message_without_usage(self) -> None:
		"""assistant messages without usage fall back to heuristic."""
		msg = AssistantMessage.from_text("response text")
		result = estimate_message_tokens(msg)
		assert result == estimate_tokens("response text")

	def test_assistant_message_zero_usage(self) -> None:
		"""zero output_tokens should fall back to heuristic."""
		msg = AssistantMessage.from_text("response text")
		msg.usage = Usage(input_tokens=0, output_tokens=0, total_tokens=0)
		result = estimate_message_tokens(msg)
		assert result == estimate_tokens("response text")

	def test_assistant_with_tool_calls(self) -> None:
		"""tool calls on assistant messages add to the estimate."""
		msg = AssistantMessage(
			content=[TextContent(text="let me search")],
			tool_calls=[
				ToolCall(name="web_search", arguments={"query": "test"}),
			],
		)
		result = estimate_message_tokens(msg)
		text_tokens = estimate_tokens("let me search")
		name_tokens = estimate_tokens("web_search")
		args_tokens = estimate_tokens('{"query": "test"}')
		assert result == text_tokens + name_tokens + args_tokens

	def test_tool_message(self) -> None:
		msg = ToolMessage(
			tool_call_id="tc_123",
			tool_output="search results here",
		)
		result = estimate_message_tokens(msg)
		assert result == estimate_tokens("search results here")

	def test_tool_message_with_attachments(self) -> None:
		msg = ToolMessage(
			tool_call_id="tc_123",
			tool_output="done",
			attachments=[ImageContent(url="https://example.com/img.png")],
		)
		result = estimate_message_tokens(msg)
		# provider loads image URL as native media.
		image_tokens = 1024
		assert result == estimate_tokens("done") + image_tokens

	def test_system_message(self) -> None:
		msg = SystemMessage.from_text("you are a helpful assistant")
		result = estimate_message_tokens(msg)
		assert result == estimate_tokens("you are a helpful assistant")

	def test_large_tool_result(self) -> None:
		"""large tool results should produce proportionally large estimates."""
		big_output = "x" * 100_000
		msg = ToolMessage(tool_call_id="tc_1", tool_output=big_output)
		result = estimate_message_tokens(msg)
		assert result == estimate_tokens(big_output)
		# should be roughly 30K tokens
		assert result > 25_000


# -- estimate_thread_tokens --


class TestEstimateThreadTokens:
	def test_empty_thread(self) -> None:
		thread = Thread(messages=[])
		assert estimate_thread_tokens(thread) == 0

	def test_thread_sums_messages(self) -> None:
		thread = Thread(
			messages=[
				UserMessage.from_text("hello"),
				AssistantMessage.from_text("hi there"),
			]
		)
		expected = estimate_tokens("hello") + estimate_tokens("hi there")
		assert estimate_thread_tokens(thread) == expected

	def test_thread_uses_real_usage(self) -> None:
		"""thread estimation should prefer real output_tokens on assistant messages."""
		assistant = AssistantMessage.from_text("response")
		assistant.usage = Usage(
			input_tokens=1000,
			output_tokens=200,
			total_tokens=1200,
		)
		thread = Thread(
			messages=[
				UserMessage.from_text("question"),
				assistant,
			]
		)
		result = estimate_thread_tokens(thread)
		assert result == estimate_tokens("question") + 200


# -- compute_available_budget --


class TestComputeAvailableBudget:
	def test_basic_budget(self) -> None:
		result = compute_available_budget(200_000)
		assert result == 200_000 - DEFAULT_RESPONSE_HEADROOM

	def test_with_system_prompt(self) -> None:
		result = compute_available_budget(200_000, system_prompt_tokens=5000)
		assert result == 200_000 - 5000 - DEFAULT_RESPONSE_HEADROOM

	def test_with_summaries(self) -> None:
		result = compute_available_budget(
			200_000,
			system_prompt_tokens=5000,
			summary_tokens=3000,
		)
		assert result == 200_000 - 5000 - 3000 - DEFAULT_RESPONSE_HEADROOM

	def test_custom_headroom(self) -> None:
		result = compute_available_budget(
			200_000,
			response_headroom=8192,
		)
		assert result == 200_000 - 8192

	def test_none_context_window_uses_default(self) -> None:
		result = compute_available_budget(None)
		assert result == DEFAULT_CONTEXT_WINDOW - DEFAULT_RESPONSE_HEADROOM

	def test_overhead_exceeds_window_floors_at_zero(self) -> None:
		result = compute_available_budget(
			1000,
			system_prompt_tokens=5000,
			response_headroom=4096,
		)
		assert result == 0

	def test_exact_fit(self) -> None:
		result = compute_available_budget(
			10_000,
			system_prompt_tokens=3000,
			summary_tokens=2000,
			response_headroom=5000,
		)
		assert result == 0
