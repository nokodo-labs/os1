"""run input validation tests."""

import pytest
from fastapi import HTTPException

from api.schemas.runs import RunInput
from api.v1.service.chat.user_message import validate_run_input


def test_validate_run_input_rejects_invisible_payload_text() -> None:
	text = "please explain " + ("\U000e0100" * 300)

	with pytest.raises(HTTPException) as exc_info:
		validate_run_input(RunInput(text=text))

	assert exc_info.value.status_code == 422
	assert (
		exc_info.value.detail
		== "input text contains too many invisible unicode characters"
	)


def test_validate_run_input_rejects_zero_width_payload_text() -> None:
	text = "please explain " + ("\u200b" * 300)

	with pytest.raises(HTTPException) as exc_info:
		validate_run_input(RunInput(text=text))

	assert exc_info.value.status_code == 422
	assert (
		exc_info.value.detail
		== "input text contains too many invisible unicode characters"
	)


def test_validate_run_input_allows_normal_emoji_variation_selectors() -> None:
	validate_run_input(RunInput(text="i love this ❤️"))


def test_validate_run_input_allows_normal_emoji_zwj_sequences() -> None:
	validate_run_input(RunInput(text="family emoji 👨‍👩‍👧‍👦"))
