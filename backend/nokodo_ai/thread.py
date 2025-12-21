"""thread domain model for SDK execution."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from nokodo_ai.base import Base
from nokodo_ai.message import Message


class Thread(Base):
	"""a conversation thread containing messages.

	this is a simple, execution-focused model.
	the API layer handles persistence and mapping to ORM.
	"""

	created_at: datetime = Field(default_factory=lambda: datetime.now(UTC)) 
	messages: list[Message] = Field(default_factory=list)

	def add(self, message: Message) -> None:
		"""append a message to the thread."""
		self.messages.append(message)
