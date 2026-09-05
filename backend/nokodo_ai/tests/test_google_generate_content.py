"""tests for Google generate_content adapter conversion."""

import base64

from nokodo_ai.adapters.google.generate_content import (
	_content_part_to_google,
	_messages_to_google,
)
from nokodo_ai.adapters.google.types import GoogleContent, GoogleFunctionResponse
from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	Message,
	ToolCall,
	ToolMessage,
)


def test_google_file_content_base64_becomes_inline_data() -> None:
	data = b"%PDF-1.7\nbody"
	part = _content_part_to_google(
		FileContent(
			base64=base64.b64encode(data).decode("ascii"),
			media_type="application/pdf",
			filename="report.pdf",
		)
	)

	assert part is not None
	assert part.inline_data is not None
	assert part.inline_data.data == data
	assert part.inline_data.mime_type == "application/pdf"


def _tool_function_response(messages: list[Message]) -> GoogleFunctionResponse:
	"""run the conversion and pull the functionResponse off the final tool turn."""
	_system, contents = _messages_to_google(messages)
	content = contents[-1]
	assert isinstance(content, GoogleContent)
	assert content.parts is not None
	fr = content.parts[0].function_response
	assert fr is not None
	return fr


def test_google_tool_message_base64_image_rides_in_function_response_part() -> None:
	"""a ToolMessage image attachment rides inside the functionResponse parts as
	inline_data (gemini-native multimodal tool result), and the structured response
	survives untouched — no flattening to a filename placeholder."""
	data = b"\x89PNG\r\n\x1a\nchart-bytes"
	assistant: Message = AssistantMessage(
		content=[],
		tool_calls=[ToolCall(id="call_1", name="render_chart", arguments="{}")],
	)
	tool: Message = ToolMessage(
		tool_call_id="call_1",
		tool_output='{"ok": true}',
		attachments=[
			ImageContent(
				base64=base64.b64encode(data).decode("ascii"),
				media_type="image/png",
				filename="chart.png",
			)
		],
	)

	fr = _tool_function_response([assistant, tool])

	assert fr.name == "render_chart"
	assert fr.response == {"ok": True}
	parts = fr.parts
	assert parts is not None and len(parts) == 1
	blob = parts[0].inline_data
	assert blob is not None
	assert blob.data == data  # raw bytes, decoded from base64
	assert blob.mime_type == "image/png"
	assert blob.display_name == "chart.png"


def test_google_tool_message_url_image_becomes_file_data_part() -> None:
	"""a url image attachment becomes a file_data functionResponse part; non-json
	tool_output is wrapped under the 'result' key."""
	assistant: Message = AssistantMessage(
		content=[],
		tool_calls=[ToolCall(id="call_2", name="fetch_image", arguments="{}")],
	)
	tool: Message = ToolMessage(
		tool_call_id="call_2",
		tool_output="see image",
		attachments=[
			ImageContent(url="https://example.com/a.png", media_type="image/png")
		],
	)

	fr = _tool_function_response([assistant, tool])

	assert fr.response == {"result": "see image"}
	parts = fr.parts
	assert parts is not None and len(parts) == 1
	file_data = parts[0].file_data
	assert file_data is not None
	assert file_data.file_uri == "https://example.com/a.png"
	assert file_data.mime_type == "image/png"


def test_google_tool_message_without_attachments_has_no_parts() -> None:
	"""text-only tool result: the functionResponse carries no media parts so gemini
	gets a plain dict-only functionResponse (parts stays None)."""
	assistant: Message = AssistantMessage(
		content=[],
		tool_calls=[ToolCall(id="call_3", name="calc", arguments="{}")],
	)
	tool: Message = ToolMessage(tool_call_id="call_3", tool_output='{"value": 42}')

	fr = _tool_function_response([assistant, tool])

	assert fr.response == {"value": 42}
	assert fr.parts is None
