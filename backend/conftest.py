"""Root conftest for Windows async compatibility."""

import asyncio
import sys
from pathlib import Path


def pytest_configure(config):
	"""Configure pytest to use Windows-compatible event loop."""
	if sys.platform == "win32":
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

	# best-effort load of .env so SDK adapter constructors can find API keys
	# (tests should still work if python-dotenv isn't installed)
	try:
		from dotenv import load_dotenv
	except ImportError:
		return

	backend_dir = Path(__file__).resolve().parent
	env_path = backend_dir / ".env"
	if env_path.exists():
		load_dotenv(env_path, override=False)
