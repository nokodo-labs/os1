"""tests for provider exception shape helpers."""

import httpx

from nokodo_ai.utils.error_mapping import error_text, response_attr


class _StreamingProviderError(Exception):
	def __init__(self, response: httpx.Response) -> None:
		super().__init__("stream error")
		self.message = "stream error"
		self.body = {
			"type": "error",
			"error": {
				"type": "api_error",
				"message": "Output blocked by content filtering policy",
			},
		}
		self.response = response


def test_unread_streaming_response_text_is_ignored() -> None:
	request = httpx.Request("POST", "https://provider.example/v1/generate")
	response = httpx.Response(
		500,
		request=request,
		stream=httpx.ByteStream(b"unread"),
	)
	exc = _StreamingProviderError(response)

	assert response_attr(exc, "text") is None
	assert error_text(exc) == (
		"stream error Output blocked by content filtering policy api_error"
	)
