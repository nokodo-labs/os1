"""server-sent events (SSE) utilities.

provides helpers for formatting and streaming SSE events in a consistent way
across the codebase.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from typing import Any

from pydantic import BaseModel
from starlette.responses import StreamingResponse


# SSE comment frame emitted when the source is idle. comment lines (leading
# ':') are ignored by every spec-compliant client, so this only keeps the
# connection warm without reaching application code.
_SSE_PING = b": ping\n\n"


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


async def sse_heartbeat(
	stream: AsyncIterator[bytes],
	interval: float = 15.0,
) -> AsyncGenerator[bytes]:
	"""interleave keep-alive ping comments into an idle SSE stream.

	when the source yields nothing for ``interval`` seconds a comment frame is
	emitted so intermediaries (proxies, load balancers) do not treat the
	connection as dead during long gaps between events. the source generator's
	cleanup still runs on disconnect via ``aclose()`` in the finally block.
	"""
	agen = stream.__aiter__()
	pending: asyncio.Task[bytes] | None = asyncio.ensure_future(agen.__anext__())
	try:
		while pending is not None:
			done, _ = await asyncio.wait({pending}, timeout=interval)
			if not done:
				# idle window elapsed - keep the same pending read alive.
				yield _SSE_PING
				continue
			try:
				frame = pending.result()
			except StopAsyncIteration:
				pending = None
				break
			yield frame
			pending = asyncio.ensure_future(agen.__anext__())
	finally:
		if pending is not None:
			pending.cancel()
			with contextlib.suppress(asyncio.CancelledError, Exception):
				await pending
		if isinstance(agen, AsyncGenerator):
			with contextlib.suppress(Exception):
				await agen.aclose()


def sse_response(
	stream: AsyncIterator[bytes],
	headers: dict[str, str] | None = None,
	heartbeat_interval: float | None = 15.0,
) -> StreamingResponse:
	"""wrap an SSE bytes stream in a StreamingResponse with correct headers.

	args:
		stream: async iterator yielding SSE-formatted bytes
		headers: optional additional headers to include
		heartbeat_interval: seconds between keep-alive pings when the source is
			idle; pass None to disable heartbeats

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
	body = (
		stream
		if heartbeat_interval is None
		else sse_heartbeat(stream, heartbeat_interval)
	)
	return StreamingResponse(
		body,
		media_type="text/event-stream",
		headers=base_headers,
	)
