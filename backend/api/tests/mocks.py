"""shared test doubles for api tests.

service modules import their dependencies as explicit symbols, so a call site
holds its own reference and patching the providing module does not intercept it.
the helpers here patch the provider plus every module that imported the symbol.
"""

import sys
from types import ModuleType

import pytest

from api.v1.service import vectorstores as vectorstores_service


def _vectorstore_bindings(names: list[str]) -> list[tuple[ModuleType, str, str]]:
	"""locate production modules holding a direct reference to the named ops.

	derived from the live modules rather than hardcoded so new call sites are
	picked up automatically. test modules are skipped: a module-level capture
	such as ``_REAL_SEARCH = vectorstores_service.search`` is a deliberate
	reference to the original, not a call site to redirect.

	must run before the provider is patched, otherwise the identity comparison
	is against the replacement and matches nothing.
	"""
	originals = {name: getattr(vectorstores_service, name) for name in names}
	targets: list[tuple[ModuleType, str, str]] = []
	for module in list(sys.modules.values()):
		name = getattr(module, "__name__", "")
		if not name.startswith("api.") or name.startswith("api.tests"):
			continue
		if module is vectorstores_service:
			continue
		for local_name, value in list(vars(module).items()):
			for provider_name, original in originals.items():
				if value is original:
					targets.append((module, local_name, provider_name))
	return targets


def patch_vectorstore_ops(
	monkeypatch: pytest.MonkeyPatch, **replacements: object
) -> None:
	"""replace vectorstore ops on the provider and on every direct importer.

	use this instead of patching ``vectorstores_service`` alone, otherwise call
	sites that imported the symbol keep the previous binding and the replacement
	never sees the calls.
	"""
	targets = _vectorstore_bindings(list(replacements))
	for provider_name, replacement in replacements.items():
		monkeypatch.setattr(vectorstores_service, provider_name, replacement)
	for module, local_name, provider_name in targets:
		monkeypatch.setattr(module, local_name, replacements[provider_name])
