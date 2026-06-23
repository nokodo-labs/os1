"""worker boot import-hygiene guard.

the taskiq worker and scheduler boot by importing ``api.v1.tasks.registry``
first, in a fresh interpreter. that import order is what surfaces circular
imports between the tasks layer and the service layer: an in-process import
inside the test suite hides them because earlier tests have already loaded the
service modules, so the cycle resolves against a fully initialised module.

these tests run the boot import in a subprocess to reproduce the real worker
order and assert every critical durable runner registers. they live outside
``api/tests`` on purpose so the heavy DB/redis autouse fixtures do not run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]

_REQUIRED_RUNNERS = (
	"file.process",
	"integrations.open_webui.import",
)


def _run_boot_script(script: str) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		[sys.executable, "-c", script],
		cwd=str(_BACKEND_ROOT),
		env=os.environ.copy(),
		capture_output=True,
		text=True,
	)


def test_task_registry_imports_in_fresh_interpreter() -> None:
	"""importing the registry first must not trip a circular import."""
	result = _run_boot_script("import api.v1.tasks.registry")
	assert result.returncode == 0, (
		"worker boot import failed (likely a circular import between the tasks "
		f"and service layers):\n{result.stderr.strip()}"
	)


def test_task_registry_registers_critical_runners() -> None:
	"""the durable runners the app relies on must register at worker boot."""
	required = ", ".join(repr(name) for name in _REQUIRED_RUNNERS)
	script = (
		"import api.v1.tasks.registry\n"
		"from api.v1.service import tasks as t\n"
		f"required = {{{required}}}\n"
		"missing = sorted(required - set(t._task_runners))\n"
		"assert not missing, f'unregistered runners: {missing}'\n"
		"print('OK')\n"
	)
	result = _run_boot_script(script)
	assert result.returncode == 0, (
		"critical task runners failed to register at worker boot:\n"
		f"{result.stdout.strip()}\n{result.stderr.strip()}"
	)
	assert "OK" in result.stdout
