"""tests for the pytest session lock."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_second_pytest_session_stops() -> None:
	environment = os.environ.copy()
	for name in (
		"PYTEST_XDIST_WORKER",
		"PYTEST_XDIST_WORKER_COUNT",
		"PYTEST_XDIST_TESTRUNUID",
	):
		environment.pop(name, None)

	backend_dir = Path(__file__).resolve().parents[1]
	result = subprocess.run(
		[
			sys.executable,
			"-m",
			"pytest",
			"--collect-only",
			"tests/test_session_lock.py",
		],
		cwd=backend_dir,
		env=environment,
		capture_output=True,
		text=True,
		check=False,
		timeout=30,
	)

	output = result.stdout + result.stderr
	assert result.returncode == pytest.ExitCode.USAGE_ERROR
	assert "another pytest session is already active" in output
