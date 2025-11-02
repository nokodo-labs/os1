"""Root conftest for Windows async compatibility."""

import asyncio
import sys


def pytest_configure(config):
	"""Configure pytest to use Windows-compatible event loop."""
	if sys.platform == "win32":
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
