"""Root conftest.

Keeps global pytest bootstrapping out of the SDK package.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def pytest_configure(config: object) -> None:
	_ = config
	if sys.platform == "win32":
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

	# best-effort load of .env so local runs can pick up API keys
	try:
		from dotenv import load_dotenv
	except ImportError:
		return

	backend_dir = Path(__file__).resolve().parent
	env_path = backend_dir / ".env"
	if env_path.exists():
		load_dotenv(env_path, override=False)
