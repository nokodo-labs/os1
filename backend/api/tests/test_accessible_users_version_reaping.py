"""every ACL-typed resource reaps its accessible-user version counter on delete.

the counters have no TTL by design: an expiring counter resets to 0 and makes
an entry invalidated at version N addressable again. so a resource that is
gone for good has to have its key DELETED, not bumped - otherwise every ACL
mutation the platform ever performs leaves a permanent key behind.

this walks `RESOURCE_CONFIG` rather than a hand-written list, because a
hand-written list is exactly what let five of these paths be missed: adding a
thirteenth ACL type must fail here until its delete path reaps too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from api.permissions import ResourceType
from api.v1.service.authorization.config import (
	RESOURCE_CONFIG,
	is_acl_resource_config,
)


_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_DROP_CALL = "enqueue_accessible_users_version_drop"

#: the delete function for each ACL-typed resource, as (module path, function).
#: hand-maintained; completeness is asserted against `RESOURCE_CONFIG` below.
_DELETE_SITES: dict[ResourceType, tuple[str, str]] = {
	ResourceType.THREAD: ("api/v1/service/threads/core.py", "execute_thread_deletion"),
	ResourceType.PROJECT: ("api/v1/service/projects.py", "delete_project"),
	ResourceType.AGENT: ("api/v1/service/agents/core.py", "delete_agent"),
	ResourceType.NOTE: ("api/v1/service/notes.py", "delete_note"),
	ResourceType.MEMORY: ("api/v1/service/memories.py", "delete_memory"),
	ResourceType.FILE: ("api/v1/service/files/core.py", "delete_file"),
	ResourceType.CALENDAR: ("api/v1/service/calendar/calendars.py", "delete_calendar"),
	ResourceType.PLUGIN: ("api/v1/service/plugins.py", "delete_plugin"),
	ResourceType.PROMPT: ("api/v1/service/prompts/service.py", "delete_prompt"),
	ResourceType.GROUP: ("api/v1/service/groups.py", "delete_group"),
	ResourceType.REMINDER_LIST: (
		"api/v1/service/reminders/lists.py",
		"delete_reminder_list",
	),
}

#: TASK has no single-instance delete anywhere; its rows go only by ORM cascade
#: from a parent, so there is no site to reap from.
_NO_DELETE_PATH: frozenset[ResourceType] = frozenset({ResourceType.TASK})


def _acl_resource_types() -> set[ResourceType]:
	return {
		resource_type
		for resource_type, config in RESOURCE_CONFIG.items()
		if is_acl_resource_config(config)
	}


def _function_source(module_path: str, function_name: str) -> str:
	"""return one function's source, so a call elsewhere in the file misses."""
	source = (_BACKEND_ROOT / module_path).read_text(encoding="utf-8")
	tree = ast.parse(source)
	for node in ast.walk(tree):
		if (
			isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
			and node.name == function_name
		):
			return ast.get_source_segment(source, node) or ""
	raise AssertionError(f"{function_name} not found in {module_path}")


def test_every_acl_resource_type_has_a_known_delete_site() -> None:
	"""the mapping above covers `RESOURCE_CONFIG`, with TASK stated as absent.

	this is the half that makes the next test meaningful: without it, dropping
	a type out of the mapping would silently stop checking it.
	"""
	covered = set(_DELETE_SITES) | _NO_DELETE_PATH
	acl_types = _acl_resource_types()

	assert acl_types - covered == set(), (
		"new ACL resource type(s) with no delete site recorded: "
		f"{sorted(t.value for t in acl_types - covered)}. add the version-counter "
		"drop to the delete path and record it here"
	)
	assert covered - acl_types == set(), (
		"delete site recorded for a type that is no longer an ACL resource: "
		f"{sorted(t.value for t in covered - acl_types)}"
	)


@pytest.mark.parametrize(
	("resource_type", "site"),
	sorted(_DELETE_SITES.items(), key=lambda item: item[0].value),
	ids=lambda value: value.value if isinstance(value, ResourceType) else "",
)
def test_each_delete_path_reaps_its_version_counter(
	resource_type: ResourceType,
	site: tuple[str, str],
) -> None:
	"""the delete function enqueues the drop, naming its own resource type.

	a static check rather than a live delete per type: the behaviour under
	test is "this call site exists", and driving eleven real deletions through
	their permission gates and cascades would test those instead.
	"""
	module_path, function_name = site
	source = _function_source(module_path, function_name)

	assert _DROP_CALL in source, (
		f"{function_name} in {module_path} does not reap the "
		f"{resource_type.value} version counter; its key survives the row"
	)
	assert f"ResourceType.{resource_type.name}" in source, (
		f"{function_name} calls {_DROP_CALL} but not for "
		f"ResourceType.{resource_type.name}"
	)


def test_task_still_has_no_delete_path() -> None:
	"""the TASK exemption is a fact about the code, not a permanent excuse.

	if a task delete is ever written, this fails and the reap has to be added
	with it.
	"""
	for module_path, function_name in (
		("api/v1/service/tasks.py", "delete_task"),
		("api/v1/routers/tasks.py", "delete_task"),
	):
		path = _BACKEND_ROOT / module_path
		if not path.exists():
			continue
		tree = ast.parse(path.read_text(encoding="utf-8"))
		names = {
			node.name
			for node in ast.walk(tree)
			if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
		}
		assert function_name not in names, (
			f"{module_path} now defines {function_name}; TASK is an ACL type, so "
			"that delete must reap its accessible-user version counter and move "
			"out of _NO_DELETE_PATH"
		)
