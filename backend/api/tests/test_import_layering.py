"""import-graph guards.

these run the interpreter in a SUBPROCESS on purpose: by the time pytest
collects this module, conftest has already imported half the app, which is
exactly what hides an import cycle. only a cold interpreter proves the graph.
"""

import subprocess
import sys


def _import_cold(statement: str) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		[sys.executable, "-c", statement],
		capture_output=True,
		text=True,
		check=False,
	)


def test_schemas_can_be_imported_before_models() -> None:
	"""``api.schemas`` must not depend on ``api.models`` being loaded first.

	regression: ``schemas/common.py`` imported ``PRIVATE_METADATA_KEY`` from
	``api.models.mixins``, which closed a schemas -> models -> schemas cycle
	(models/agent.py imports schemas/agent.py). the whole suite still passed
	because conftest imports a model before any schema, so the failing order
	was never exercised. shared constants belong in a leaf module.
	"""
	result = _import_cold("import api.schemas")
	assert result.returncode == 0, result.stderr


def test_models_can_be_imported_before_schemas() -> None:
	"""the reverse order must keep working too."""
	result = _import_cold("import api.models")
	assert result.returncode == 0, result.stderr


def test_runs_invocation_imports_cold() -> None:
	"""``runs.invocation`` must reach threads and run siblings at module scope.

	it sits above threads and run internals, so a cycle here is the signal that
	the layering is wrong. a lazy import inside a function would hide exactly that.
	"""
	result = _import_cold("import api.v1.service.runs.invocation")
	assert result.returncode == 0, result.stderr


def test_threads_facade_imports_cold() -> None:
	"""``api.v1.service.threads`` must not need runs loaded first."""
	result = _import_cold("import api.v1.service.threads")
	assert result.returncode == 0, result.stderr


def test_runs_facade_imports_cold() -> None:
	"""the eager runs facade must work before any chat or run submodule import."""
	result = _import_cold("import api.v1.service.runs")
	assert result.returncode == 0, result.stderr


def test_task_registry_imports_cold() -> None:
	"""the taskiq registry pulls the same graph from a worker process."""
	result = _import_cold("import api.v1.tasks.registry")
	assert result.returncode == 0, result.stderr
