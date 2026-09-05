"""base hook class for sdk-compatible hooks."""

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.session_release import releasing_session
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext
from nokodo_ai.hooks import Hook as SDKHook


class Hook(SDKHook[AppContext]):
	"""sdk Hook specialized to AppContext.

	subclasses implement ``run``; ``execute`` is the SDK entry point and stays
	final so the borrowed connection is always returned.
	"""

	async def execute(
		self,
		state: AgentIterationSnapshot[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> None:
		async with releasing_session(app_context):
			await self.run(state, agent_context, app_context)

	async def run(
		self,
		state: AgentIterationSnapshot[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> None:
		"""observe the iteration; see ``nokodo_ai.hooks.Hook.execute``."""
		raise NotImplementedError("run method must be implemented by subclasses")
