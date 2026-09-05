"""asyncio event loop selection helpers.

some libraries require selector-based event loops, which are not the
default on windows (proactor). policies are deprecated in python 3.14 and
removed in 3.16; drop the policy helper once all consumers accept explicit
loop factories.
"""

import asyncio
import selectors
import sys


def configure_windows_selector_event_loop_policy() -> None:
	"""force selector loops process-wide on windows via the loop policy.

	the policy is the only mechanism when a framework creates its own loops
	with no way to inject a loop factory. no-op off windows.
	"""
	if sys.platform != "win32":
		return

	policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
	if policy_factory is None:
		return

	asyncio.set_event_loop_policy(policy_factory())


def selector_loop_factory() -> asyncio.AbstractEventLoop:
	"""loop factory that returns a selector-based loop."""
	return asyncio.SelectorEventLoop(selectors.SelectSelector())
