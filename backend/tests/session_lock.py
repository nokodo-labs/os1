"""prevents overlapping pytest controller sessions in one checkout."""

import os

import pytest
from _pytest.config import Config
from filelock import FileLock, Timeout


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Config) -> None:
	if os.getenv("PYTEST_XDIST_WORKER"):
		return

	lock_path = config.rootpath / "data" / ".pytest-session.lock"
	lock = FileLock(lock_path, timeout=0)
	try:
		lock.acquire()
	except Timeout as error:
		raise pytest.UsageError(
			f"another pytest session is already active for {config.rootpath}"
		) from error
	config.add_cleanup(lock.release)
