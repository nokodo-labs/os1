"""SDK-level hooks for post-agent execution."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field

from .base import Base
from .threads import Thread


class Hook[AppContextT = None](Base, ABC):
	"""base class for hooks.

	hooks run AFTER an agent has finished processing (after all tool calls
	and the final response). they receive the complete thread but CANNOT
	modify anything - they are read-only observers.

	hooks are generic over AppContextT, allowing application-specific
	context to be passed through the entire agent execution pipeline.

	common uses:
	- logging and analytics
	- memory extraction and storage
	- notifications and webhooks
	- audit trails
	"""

	name: str = Field(..., description="unique hook identifier")
	description: str = Field(default="", description="what this hook does")

	@abstractmethod
	async def execute(
		self,
		thread: Thread,
		app_context: AppContextT | None,
	) -> None:
		"""execute the hook after agent completion.

		args:
			thread: the complete conversation thread (read-only)
			app_context: application-specific context

		returns:
			None - hooks cannot modify anything, only observe
		"""
		raise NotImplementedError("execute method must be implemented by subclasses")
