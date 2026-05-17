"""chat tool registry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from api.v1.service.chat.tools.agentic_web_search import AgenticWebSearchTool
from api.v1.service.chat.tools.calendar import (
	CalendarEventGetTool,
	CalendarEventWriteTool,
)
from api.v1.service.chat.tools.code_interpreter import CodeInterpreterTool
from api.v1.service.chat.tools.files import FileEditTool, FileGetTool
from api.v1.service.chat.tools.image_generation import GenerateImageTool
from api.v1.service.chat.tools.memories import (
	MemoryCreateTool,
	MemoryRecallTool,
)
from api.v1.service.chat.tools.notes import NoteGetTool, NoteWriteTool
from api.v1.service.chat.tools.projects import ProjectGetTool
from api.v1.service.chat.tools.reminders import (
	ReminderGetTool,
	ReminderWriteTool,
)
from api.v1.service.chat.tools.reveal_attachment import RevealAttachmentTool
from api.v1.service.chat.tools.send_notification import SendNotificationTool
from api.v1.service.chat.tools.think import ThinkingTool
from api.v1.service.chat.tools.web_search import FetchUrlTool, WebSearchTool
from nokodo_ai.tool import Tool


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


logger = logging.getLogger(__name__)


_TOOLS: list[Tool[AppContext]] = [
	MemoryRecallTool(),
	MemoryCreateTool(),
	NoteGetTool(),
	NoteWriteTool(),
	ProjectGetTool(),
	ReminderGetTool(),
	ReminderWriteTool(),
	CalendarEventGetTool(),
	CalendarEventWriteTool(),
	FileGetTool(),
	FileEditTool(),
	WebSearchTool(),
	AgenticWebSearchTool(),
	FetchUrlTool(),
	GenerateImageTool(),
	# GenerateVideoTool(), WIP
	# GenerateAudioTool(), WIP
	CodeInterpreterTool(),
	RevealAttachmentTool(),
	SendNotificationTool(),
	ThinkingTool(),
]

TOOL_REGISTRY: dict[str, Tool[AppContext]] = {t.name: t for t in _TOOLS}
if len(TOOL_REGISTRY) != len(_TOOLS):
	raise ValueError("duplicate tool names detected in TOOL_REGISTRY")


def get_registered_names() -> frozenset[str]:
	"""return registered tool names."""
	return frozenset(tool.name for tool in TOOL_REGISTRY.values())


async def resolve_tools(
	tool_ids: list[str],
) -> list[Tool[AppContext]]:
	"""resolve tool ids to instantiated Tool objects."""
	tools: list[Tool[AppContext]] = []
	for tool_id in tool_ids:
		tool = TOOL_REGISTRY.get(tool_id)
		if tool is None:
			logger.warning("unknown tool id requested: %s", tool_id)
			continue
		tools.append(tool)
	return tools


__all__ = [
	"TOOL_REGISTRY",
	"get_registered_names",
	"resolve_tools",
]
