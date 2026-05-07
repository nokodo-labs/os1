"""SDK-level hooks for post-agent execution."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field

from .base import Base
from .context import AgentContext
from .threads import Thread


class Hook[AppContextT = None](Base, ABC):
	"""base class for hooks.

	hooks run after each assistant response is appended to the thread.
	they receive the current thread but CANNOT modify anything - they are
	read-only observers.

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
		agent_context: AgentContext,
		app_context: AppContextT | None,
	) -> None:
		"""execute the hook after an assistant response.

		args:
			thread: the current conversation thread (read-only)
			agent_context: runtime context for this agent iteration
			app_context: application-specific context

		returns:
			None - hooks cannot modify anything, only observe
		"""
		raise NotImplementedError("execute method must be implemented by subclasses")
