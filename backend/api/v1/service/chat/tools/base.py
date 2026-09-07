"""base tool class for sdk-compatible tools."""

from typing import final

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.session_release import releasing_session
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool as SDKTool


class Tool(SDKTool[AppContext]):
	"""sdk Tool specialized to AppContext.

	subclasses implement ``run``; ``call`` is the SDK entry point and stays
	final so the borrowed connection is always returned.
	"""

	@final
	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		async with releasing_session(__app_context__):
			return await self.run(
				__state__,
				__agent_context__,
				__tool_call_context__,
				__app_context__,
				**kwargs,
			)

	async def run(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		"""execute the tool; see ``nokodo_ai.tool.Tool.call``."""
		raise NotImplementedError("run method must be implemented by subclasses")
