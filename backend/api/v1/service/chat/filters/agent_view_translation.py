"""agent-to-agent context view translation."""

from pydantic import Field

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext


class AgentViewTranslationFilter(Filter):
	"""translate other agents' run output into its user-visible view."""

	name: str = Field(default="agent_view_translation")
	description: str = Field(
		default="translates other agents' output into its user-visible context view"
	)

	async def run(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		_ = agent_context, app_context
		return state
