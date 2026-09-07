"""base filter class for sdk-compatible filters."""

from typing import final

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.session_release import releasing_session
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.filters import Filter as SDKFilter
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread


class Filter(SDKFilter[AppContext]):
	"""sdk Filter specialized to AppContext.

	subclasses implement ``run``; ``process`` is the SDK entry point and stays
	final so the borrowed connection is always returned.
	"""

	@final
	async def process(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		async with releasing_session(app_context):
			return await self.run(state, agent_context, app_context)

	async def run(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""filter the iteration state; see ``nokodo_ai.filters.Filter.process``."""
		raise NotImplementedError("run method must be implemented by subclasses")

	@staticmethod
	def _replace_sentinel(
		thread: SDKThread,
		sentinel: str,
		replacement: str,
	) -> bool:
		"""replace a sentinel string in the system message, in-place.

		returns True if the sentinel was found and replaced, False otherwise.
		"""
		for i, m in enumerate(thread.messages):
			if not isinstance(m, SDKSystemMessage):
				continue
			text = m.text
			if not text or sentinel not in text:
				continue
			thread.messages[i] = SDKSystemMessage.from_text(
				text.replace(sentinel, replacement)
			)
			return True
		return False
