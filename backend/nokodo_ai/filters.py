"""SDK-level filters for pre-processing agent messages."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field

from .base import Base
from .threads import Thread


class Filter[AppContextT = None](Base, ABC):
	"""base class for filters.

	filters run BEFORE an agent sends messages to the model.
	they can modify, augment, or filter the input messages.

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
		thread: Thread,
		app_context: AppContextT | None,
	) -> Thread:
		"""process messages through this filter.

		args:
			thread: the current conversation thread
			app_context: application-specific context

		returns:
			processed thread (may be modified, augmented, or filtered)
		"""
		raise NotImplementedError("process method must be implemented by subclasses")
