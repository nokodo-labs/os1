"""thread domain model for SDK execution."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from .base import Base
from .messages import (
	AssistantMessage,
	Message,
	SystemMessage,
	ToolMessage,
	UserMessage,
)
from .types.json import JSONObject


class Thread(Base):
	"""a conversation thread containing messages.

	this is a simple, execution-focused model.
	the API layer handles persistence and mapping to ORM.
	"""

	created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
	messages: list[Message] = Field(default_factory=list)
	metadata: JSONObject | None = None

	def add(self, message: Message) -> None:
		"""append a message to the thread."""
		self.messages.append(message)

	@property
	def system_message(self) -> SystemMessage | None:
		"""return the first system message, or None."""
		for m in self.messages:
			if isinstance(m, SystemMessage):
				return m
		return None

	def recent_turns(self, k: int) -> list[str]:
		"""extract the k most recent conversation turns.

		a turn is a contiguous block of messages from the same side:
		- user turn: all text from consecutive UserMessages.
		- assistant turn: all text from consecutive AssistantMessages.

		system and tool messages are skipped (not counted as turns).
		returns turns in chronological order (oldest first).
		"""
		turns: list[str] = []
		current_role: str | None = None
		current_texts: list[str] = []

		for msg in self.messages:
			if isinstance(msg, (SystemMessage, ToolMessage)):
				continue
			if not isinstance(msg, (UserMessage, AssistantMessage)):
				continue
			role = msg.role
			if role != current_role:
				if current_texts:
					turns.append("\n".join(current_texts))
				current_role = role
				current_texts = []
			text = msg.text
			if text:
				current_texts.append(text)

		if current_texts:
			turns.append("\n".join(current_texts))

		return turns[-k:] if k < len(turns) else turns
