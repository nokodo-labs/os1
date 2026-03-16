"""runtime configuration.

keep cross-cutting runtime tweaks in one place (entrypoints call into this).
"""

from __future__ import annotations

import asyncio
import selectors
import sys


def configure_psycopg_asyncio_event_loop_policy() -> None:
	"""ensure psycopg runs on a selector event loop on windows.

	psycopg async mode is not compatible with Windows' ProactorEventLoop.
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
