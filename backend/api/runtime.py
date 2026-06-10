"""runtime configuration.

keep cross-cutting runtime tweaks in one place (entrypoints call into this).
"""

from __future__ import annotations

import asyncio
import selectors
import sys


def configure_psycopg_asyncio_event_loop_policy() -> None:
	"""force a selector event loop for taskiq's CLI on windows.

	taskiq creates its own loop with no way to inject a loop factory, so the
	event loop policy is the only mechanism to keep it on a psycopg-compatible
	selector loop. policies are deprecated in python 3.14 and removed in 3.16;
	drop this once taskiq supports explicit event loops. no-op off windows.
	"""
	if sys.platform != "win32":
		return

	policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
	if policy_factory is None:
		return

	asyncio.set_event_loop_policy(policy_factory())


def selector_loop_factory() -> asyncio.AbstractEventLoop:
	"""loop factory that returns a selector-based loop.

	this is required on windows because psycopg async is incompatible with
	proactor-based event loops.
	"""
	return asyncio.SelectorEventLoop(selectors.SelectSelector())
