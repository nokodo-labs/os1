from __future__ import annotations

import json

from api.v1.service.chat.filters.attachment_decay import _reference_attachment_text
from nokodo_ai.messages import ImageContent


def test_reference_attachment_text_includes_description() -> None:
	part = ImageContent(metadata={"description": "diagram of the auth flow"})

	result = _reference_attachment_text("auth.png", part)

	assert result == (
		'attachment_ref {"name":"auth.png","summary":"diagram of the auth flow"}'
	)


def test_reference_attachment_text_without_description() -> None:
	part = ImageContent()

	result = _reference_attachment_text("auth.png", part)

	assert result == 'attachment_ref {"name":"auth.png"}'


def test_reference_attachment_text_json_delimits_description() -> None:
	part = ImageContent(
		metadata={
			"file_id": "file_123",
			"description": "quote ' ] } and newline\ninside",
		}
	)

	result = _reference_attachment_text("auth.png", part)
	payload = json.loads(result.removeprefix("attachment_ref "))

	assert payload == {
		"id": "file_123",
		"name": "auth.png",
		"summary": "quote ' ] } and newline inside",
	}
