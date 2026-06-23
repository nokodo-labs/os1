"""tests for SSE utilities, focused on the heartbeat wrapper."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from nokodo_ai.utils.sse import _SSE_PING, sse_heartbeat


async def test_heartbeat_passes_frames_without_pings_when_fast() -> None:
	"""a source that yields promptly should not get any pings injected."""

	async def source() -> AsyncIterator[bytes]:
		yield b"a"
		yield b"b"

	out = [frame async for frame in sse_heartbeat(source(), interval=1.0)]
	assert out == [b"a", b"b"]


async def test_heartbeat_injects_ping_during_idle_gap() -> None:
	"""a gap longer than the interval should produce a ping between frames."""

	async def source() -> AsyncIterator[bytes]:
		yield b"first"
		await asyncio.sleep(0.05)
		yield b"second"

	out = [frame async for frame in sse_heartbeat(source(), interval=0.01)]
	assert out[0] == b"first"
	assert _SSE_PING in out
	assert out[-1] == b"second"


async def test_heartbeat_propagates_source_exception() -> None:
	"""errors raised by the source must surface to the consumer."""

	async def source() -> AsyncIterator[bytes]:
		yield b"x"
		raise RuntimeError("boom")

	with pytest.raises(RuntimeError, match="boom"):
		_ = [frame async for frame in sse_heartbeat(source(), interval=1.0)]


async def test_heartbeat_closes_source_on_early_break() -> None:
	"""abandoning the wrapper must run the source generator's cleanup."""
	closed = False

	async def source() -> AsyncIterator[bytes]:
		nonlocal closed
		try:
			while True:
				yield b"tick"
				await asyncio.sleep(0.01)
		finally:
			closed = True

	agen = sse_heartbeat(source(), interval=1.0)
	first = await agen.__anext__()
	assert first == b"tick"
	await agen.aclose()
	assert closed is True
