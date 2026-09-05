"""run input validation tests."""

import pytest
from fastapi import HTTPException

from api.schemas.message import MessageCreate, TextContent
from api.v1.service.chat.messages import validate_message_input


def test_validate_message_input_rejects_invisible_payload_text() -> None:
	text = "please explain " + ("\U000e0100" * 300)

	with pytest.raises(HTTPException) as exc_info:
		validate_message_input(MessageCreate(content=[TextContent(text=text)]))

	assert exc_info.value.status_code == 422
	assert (
		exc_info.value.detail
		== "input text contains too many invisible unicode characters"
	)


def test_validate_message_input_rejects_zero_width_payload_text() -> None:
	text = "please explain " + ("\u200b" * 300)

	with pytest.raises(HTTPException) as exc_info:
		validate_message_input(MessageCreate(content=[TextContent(text=text)]))

	assert exc_info.value.status_code == 422
	assert (
		exc_info.value.detail
		== "input text contains too many invisible unicode characters"
	)


def test_validate_message_input_allows_normal_emoji_variation_selectors() -> None:
	validate_message_input(MessageCreate(content=[TextContent(text="i love this ❤️")]))


def test_validate_message_input_allows_normal_emoji_zwj_sequences() -> None:
	validate_message_input(
		MessageCreate(content=[TextContent(text="family emoji 👨‍👩‍👧‍👦")])
	)
