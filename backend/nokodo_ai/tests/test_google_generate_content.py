"""tests for Google generate_content adapter conversion."""

import base64

from nokodo_ai.adapters.google.generate_content import _content_part_to_google
from nokodo_ai.messages import FileContent


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
