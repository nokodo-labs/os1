"""tests for event loop selection helpers."""

import asyncio

import pytest

from nokodo_ai.utils import event_loop


def test_policy_helper_noop_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
	"""the policy helper must not touch the policy on non-windows platforms."""
	called = False

	def _mark_called(policy: object) -> None:
		nonlocal called
		called = True

	monkeypatch.setattr(event_loop.sys, "platform", "linux")
	monkeypatch.setattr(event_loop.asyncio, "set_event_loop_policy", _mark_called)
	event_loop.configure_windows_selector_event_loop_policy()
	assert called is False


def test_selector_loop_factory_returns_selector_loop() -> None:
	loop = event_loop.selector_loop_factory()
	try:
		assert isinstance(loop, asyncio.SelectorEventLoop)
	finally:
		loop.close()
