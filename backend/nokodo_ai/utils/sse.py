"""server-sent events (SSE) utilities.

provides helpers for formatting and streaming SSE events in a consistent way
across the codebase.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from pydantic import BaseModel
from starlette.responses import StreamingResponse


def sse_encode(
	event: str,
	data: Mapping[str, Any] | BaseModel | None = None,
) -> bytes:
	"""format a single SSE event as bytes.

	args:
		event: the event type name (e.g. 'message_created', 'delta', 'done')
		data: optional payload to include in the data field. can be a dict,
			a pydantic model, or None.

	returns:
		bytes ready to write to an SSE stream

	example:
		>>> sse_encode(event='done', data={'ok': True})
		b'event: done\\ndata: {"ok":true}\\n\\n'
	"""
	if data is None:
		payload = "{}"
	elif isinstance(data, BaseModel):
		payload = data.model_dump_json(by_alias=True)
	else:
		payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
	return f"event: {event}\ndata: {payload}\n\n".encode()


def sse_error(message: str) -> bytes:
	"""shorthand for encoding an error event."""
	return sse_encode(event="error", data={"message": message})


def sse_done() -> bytes:
	"""shorthand for encoding a done event (empty data)."""
	return sse_encode(event="done", data={})


def sse_response(
	stream: AsyncIterator[bytes],
	headers: dict[str, str] | None = None,
) -> StreamingResponse:
	"""wrap an SSE bytes stream in a StreamingResponse with correct headers.

	args:
		stream: async iterator yielding SSE-formatted bytes
		headers: optional additional headers to include

	returns:
		a ready-to-return StreamingResponse
	"""
	base_headers = {
		"Cache-Control": "no-cache",
		"Connection": "keep-alive",
		"X-Accel-Buffering": "no",  # disable nginx buffering
	}
	if headers:
		base_headers.update(headers)
	return StreamingResponse(
		stream,
		media_type="text/event-stream",
		headers=base_headers,
	)
