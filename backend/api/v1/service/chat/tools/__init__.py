"""chat tools package - tool implementations for agent execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nokodo_ai.tool import Tool


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


from api.v1.service.chat.tools.memories import MemoryCreateTool, MemoryRecallTool
from api.v1.service.chat.tools.reveal_attachment import RevealAttachmentTool
from api.v1.service.chat.tools.send_notification import SendNotificationTool
from api.v1.service.chat.tools.think import ThinkingTool


_TOOLS: list[Tool[AppContext]] = [
	MemoryRecallTool(),
	MemoryCreateTool(),
	RevealAttachmentTool(),
	SendNotificationTool(),
	ThinkingTool(),
]

TOOL_REGISTRY: dict[str, Tool[AppContext]] = {}
for tool in _TOOLS:
	if tool.name in TOOL_REGISTRY:
		raise ValueError(f"duplicate tool name: {tool.name}")
	TOOL_REGISTRY[tool.name] = tool


def get_registered_names() -> frozenset[str]:
	"""return registered tool names."""
	return frozenset(tool.name for tool in TOOL_REGISTRY.values())


async def resolve_tools(
	tool_ids: list[str],
	*,
	context: AppContext,
) -> list[Tool[AppContext]]:
	"""resolve tool ids to instantiated Tool objects.

	args:
		tool_ids: list of tool identifiers to resolve
		context: agent execution context

	returns:
		list of instantiated Tool objects
	"""
	tools: list[Tool[AppContext]] = []

	for tool_id in tool_ids:
		tool = TOOL_REGISTRY.get(tool_id)
		if tool is None:
			continue

		tools.append(tool)
	return tools


__all__ = [
	"MemoryRecallTool",
	"MemoryCreateTool",
	"RevealAttachmentTool",
	"SendNotificationTool",
	"ThinkingTool",
	"TOOL_REGISTRY",
	"get_registered_names",
	"resolve_tools",
]
