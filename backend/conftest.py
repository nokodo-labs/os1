"""Root conftest.

Keeps global pytest bootstrapping out of the SDK package.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path


def pytest_asyncio_loop_factories() -> (
	dict[str, Callable[[], asyncio.AbstractEventLoop]] | None
):
	# psycopg cannot run on the Windows Proactor loop, so force the selector loop
	if sys.platform == "win32":
		return {"selector": asyncio.SelectorEventLoop}
	return None


def pytest_configure(config: object) -> None:
	_ = config
	# best-effort load of .env so local runs can pick up API keys
	try:
		from dotenv import load_dotenv
	except ImportError:
		return

	backend_dir = Path(__file__).resolve().parent
	env_path = backend_dir / ".env"
	if env_path.exists():
		load_dotenv(env_path, override=False)
