"""Coverage-focused tests for native/plugin service helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.plugin import Plugin, PluginType
from api.schemas.plugin import PluginCreate
from api.v1.service import plugins as plugin_service


class _FakePrincipal:
	"""minimal principal stub that bypasses permission checks."""

	is_admin = True
	user = SimpleNamespace(id="admin")
	user_id = "admin"
	group_ids: list[str] = []
	role_ids: tuple[str, ...] = ()
	role_resource_defaults: dict[str, str] = {}
	global_action_permissions: frozenset[str] = frozenset()

	def has_permission(self, permission: str) -> bool:
		return True


_admin = _FakePrincipal()


def test_list_native_description_fallbacks(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class DocFilter:
		"""first line doc."""

		name = "doc-filter"
		description = ""

	class NoDocHook:
		name = "no-doc-hook"
		description = ""

	class DocHook:
		"""hook doc line."""

		name = "doc-hook"
		description = ""

	class NoDocFilter:
		name = "no-doc-filter"
		description = ""

	monkeypatch.setattr(
		plugin_service,
		"TOOL_REGISTRY",
		{"tool_1": SimpleNamespace(name="t", description="tool desc")},
	)
	monkeypatch.setattr(
		plugin_service,
		"FILTER_REGISTRY",
		{"filter_1": DocFilter(), "filter_2": NoDocFilter()},
	)
	monkeypatch.setattr(
		plugin_service,
		"HOOK_REGISTRY",
		{"hook_1": NoDocHook(), "hook_2": DocHook()},
	)

	plugins = plugin_service._list_native()
	assert {p.type for p in plugins} == {"tool", "filter", "hook"}

	# tools now also go through _build_native_info
	tool_info = next(p for p in plugins if p.type == "tool")
	assert tool_info.description == "tool desc"

	filter_info = next(p for p in plugins if p.id == "filter_1")
	assert filter_info.description == "first line doc."
	filter_no_doc = next(p for p in plugins if p.id == "filter_2")
	assert filter_no_doc.description.endswith(" filter")

	hook_info = next(p for p in plugins if p.id == "hook_1")
	assert hook_info.description.endswith(" hook")
	hook_doc = next(p for p in plugins if p.id == "hook_2")
	assert hook_doc.description == "hook doc line."


def test_list_native_type_filter(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(
		plugin_service,
		"TOOL_REGISTRY",
		{"tool_1": SimpleNamespace(name="t", description="tool desc")},
	)
	monkeypatch.setattr(
		plugin_service,
		"FILTER_REGISTRY",
		{"filter_1": SimpleNamespace(name="f", description="filter desc")},
	)
	monkeypatch.setattr(
		plugin_service,
		"HOOK_REGISTRY",
		{"hook_1": SimpleNamespace(name="h", description="hook desc")},
	)

	assert {p.type for p in plugin_service._list_native("tool")} == {"tool"}
	assert {p.type for p in plugin_service._list_native("filter")} == {"filter"}
	assert {p.type for p in plugin_service._list_native("hook")} == {"hook"}


def test_get_native_variants(monkeypatch: pytest.MonkeyPatch) -> None:
	class DocFilter:
		"""doc filter."""

		name = "doc-filter"
		description = ""

	class NoDocFilter:
		name = "no-doc-filter"
		description = ""

	class DescribedFilter:
		name = "described-filter"
		description = "already described"

	class DocHook:
		"""doc hook."""

		name = "doc-hook"
		description = ""

	class NoDocHook:
		name = "no-doc-hook"
		description = ""

	class DescribedHook:
		name = "described-hook"
		description = "already described"

	monkeypatch.setattr(
		plugin_service,
		"TOOL_REGISTRY",
		{"tool_1": SimpleNamespace(name="t", description="tool desc")},
	)
	monkeypatch.setattr(
		plugin_service,
		"FILTER_REGISTRY",
		{
			"filter_1": DocFilter(),
			"filter_2": NoDocFilter(),
			"filter_3": DescribedFilter(),
		},
	)
	monkeypatch.setattr(
		plugin_service,
		"HOOK_REGISTRY",
		{
			"hook_1": DocHook(),
			"hook_2": NoDocHook(),
			"hook_3": DescribedHook(),
		},
	)

	# tools now go through _build_native_info too
	tool_info = plugin_service._get_native("tool_1")
	assert tool_info is not None
	assert tool_info.type == "tool"
	assert tool_info.description == "tool desc"

	filter_info = plugin_service._get_native("filter_1")
	assert filter_info is not None
	assert filter_info.type == "filter"
	assert filter_info.description == "doc filter."

	filter_no_doc = plugin_service._get_native("filter_2")
	assert filter_no_doc is not None
	assert filter_no_doc.type == "filter"
	assert filter_no_doc.description.endswith(" filter")

	filter_described = plugin_service._get_native("filter_3")
	assert filter_described is not None
	assert filter_described.type == "filter"
	assert filter_described.description == "already described"

	hook_info = plugin_service._get_native("hook_1")
	assert hook_info is not None
	assert hook_info.type == "hook"
	assert hook_info.description == "doc hook."

	hook_no_doc = plugin_service._get_native("hook_2")
	assert hook_no_doc is not None
	assert hook_no_doc.type == "hook"
	assert hook_no_doc.description.endswith(" hook")

	hook_described = plugin_service._get_native("hook_3")
	assert hook_described is not None
	assert hook_described.type == "hook"
	assert hook_described.description == "already described"
	assert plugin_service._get_native("missing") is None


def test_is_native_name_collision(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(
		plugin_service,
		"get_tool_names",
		lambda: frozenset({"my-tool"}),
	)
	monkeypatch.setattr(plugin_service, "get_filter_names", lambda: frozenset())
	monkeypatch.setattr(plugin_service, "get_hook_names", lambda: frozenset())

	assert plugin_service._is_native_name("my-tool") is True
	assert plugin_service._is_native_name("other-name") is False


@pytest.mark.asyncio
async def test_list_plugins_with_native_filters_db_by_type(
	db_session: AsyncSession,
) -> None:
	await plugin_service.create_plugin(
		PluginCreate(
			name="db-tool",
			description="d",
			type=PluginType.TOOL,
			author=None,
			version=None,
			source_code="code",
		),
		db_session,
		principal=_admin,  # type: ignore[arg-type]
	)
	await plugin_service.create_plugin(
		PluginCreate(
			name="db-filter",
			description="d",
			type=PluginType.FILTER,
			author=None,
			version=None,
			source_code="code",
		),
		db_session,
		principal=_admin,  # type: ignore[arg-type]
	)

	filtered = await plugin_service.list_plugins(  # type: ignore[call-overload]
		db_session,
		principal=_admin,  # type: ignore[arg-type]
		include_native=True,
		plugin_type="tool",
	)
	assert any(p.is_native for p in filtered)
	assert [p for p in filtered if not p.is_native and p.name == "db-tool"]
	assert not [p for p in filtered if not p.is_native and p.name == "db-filter"]


@pytest.mark.asyncio
async def test_list_plugins_with_native_merges_db_plugins(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(plugin_service, "TOOL_REGISTRY", {})
	monkeypatch.setattr(plugin_service, "FILTER_REGISTRY", {})
	monkeypatch.setattr(plugin_service, "HOOK_REGISTRY", {})

	tool_plugin = Plugin(
		name="db-tool",
		description=None,
		type=PluginType.TOOL,
		author=None,
		version=None,
		source_code="x",
	)
	filter_plugin = Plugin(
		name="db-filter",
		description="d",
		type=PluginType.FILTER,
		author=None,
		version=None,
		source_code="x",
	)

	db_session.add(tool_plugin)
	db_session.add(filter_plugin)
	await db_session.commit()

	all_plugins = await plugin_service.list_plugins(  # type: ignore[call-overload]
		db_session,
		principal=_admin,  # type: ignore[arg-type]
		include_native=True,
	)
	assert any(p.is_native is False and p.name == "db-tool" for p in all_plugins)

	only_tools = await plugin_service.list_plugins(  # type: ignore[call-overload]
		db_session,
		principal=_admin,  # type: ignore[arg-type]
		include_native=True,
		plugin_type="tool",
	)
	assert {p.type for p in only_tools} == {"tool"}
	assert all(p.name == "db-tool" for p in only_tools)
