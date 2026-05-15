"""SDK-level filters for pre-processing agent messages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import Field

from .base import Base
from .context import AgentContext


if TYPE_CHECKING:
	from .agents import AgentIterationState


class Filter[AppContextT = None](Base, ABC):
	"""base class for filters.

	filters run before an agent sends messages to the model.
	they can modify, augment, or filter the iteration state.

	filters are generic over AppContextT, allowing application-specific
	context to be passed through the entire agent execution pipeline.

	common uses:
	- injecting context (memories, user preferences)
	- modifying system prompts
	- adding retrieval-augmented context
	- input sanitization
	"""

	name: str = Field(..., description="unique filter identifier")
	description: str = Field(default="", description="what this filter does")

	@abstractmethod
	async def process(
		self,
		state: AgentIterationState[AppContextT],
		agent_context: AgentContext,
		app_context: AppContextT | None,
	) -> AgentIterationState[AppContextT]:
		"""process iteration state through this filter.

		args:
			state: the current iteration state
			agent_context: runtime context for this agent iteration
			app_context: application-specific context

		returns:
			processed iteration state
		"""
		raise NotImplementedError("process method must be implemented by subclasses")
