"""chat hooks package - registry + resolution for sdk hooks."""

from __future__ import annotations

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.hooks.base import Hook
from nokodo_ai.hooks import Hook as SDKHook


type AppHook = SDKHook[AppContext]


HOOK_REGISTRY: dict[str, AppHook] = {
	# no hooks registered yet
	# add hooks here as they are implemented
}


def resolve_hooks(hook_ids: list[str]) -> list[AppHook]:
	"""resolve hook ids to instantiated sdk Hook objects."""
	hooks: list[AppHook] = []
	for hook_id in hook_ids:
		hook = HOOK_REGISTRY.get(hook_id)
		if hook is None:
			continue
		hooks.append(hook)
	return hooks


__all__ = [
	"Hook",
	"HOOK_REGISTRY",
	"resolve_hooks",
]
