"""user message timestamp filter - prepends created_at to user messages."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import CREATED_AT_KEY, SENDER_USER_ID_KEY
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import Message, TextContent, UserContentPart
from nokodo_ai.messages import UserMessage as SDKUserMessage


class UserMessageTimestampFilter(Filter):
	"""prepends the original created_at timestamp to each user message."""

	name: str = Field(default="user_message_timestamp")
	description: str = Field(
		default="prepends the original UTC date and time to every user message"
	)

	_APPLIED_KEY = "_timestamped"

	async def process(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""prepend each user message with its persisted creation timestamp."""
		_ = (agent_context, app_context)
		thread = state.thread
		new_messages: list[Message] = []
		last_user_author: str | None = None
		last_user_timestamp: str | None = None
		for msg in thread.messages:
			if not isinstance(msg, SDKUserMessage):
				new_messages.append(msg)
				last_user_author = None
				last_user_timestamp = None
				continue

			timestamp = self._resolve_timestamp(msg)
			author = self._resolve_author(msg)

			if (msg.metadata or {}).get(self._APPLIED_KEY):
				new_messages.append(msg)
				last_user_author = author
				last_user_timestamp = timestamp
				continue

			if timestamp is None:
				new_messages.append(msg)
				last_user_author = author
				last_user_timestamp = None
				continue

			if author == last_user_author and timestamp == last_user_timestamp:
				new_messages.append(msg)
				continue

			prefix = f"[{timestamp}] "

			new_content: list[UserContentPart] = []
			prefixed = False
			for part in msg.content:
				if not prefixed and isinstance(part, TextContent):
					new_content.append(TextContent(text=prefix + part.text))
					prefixed = True
				else:
					new_content.append(part)

			if not prefixed:
				new_content.insert(0, TextContent(text=prefix.rstrip()))

			new_meta = {**(msg.metadata or {}), self._APPLIED_KEY: True}
			new_messages.append(
				msg.model_copy(update={"content": new_content, "metadata": new_meta})
			)
			last_user_author = author
			last_user_timestamp = timestamp

		thread.messages = new_messages
		return state

	@staticmethod
	def _resolve_timestamp(msg: SDKUserMessage) -> str | None:
		"""extract created_at from private message metadata, or None if absent."""
		metadata = msg.metadata or {}
		iso = metadata.get(CREATED_AT_KEY)
		if not isinstance(iso, str):
			return None
		dt = datetime.fromisoformat(iso)
		return dt.strftime("%Y-%m-%d %H:%M UTC")

	@staticmethod
	def _resolve_author(msg: SDKUserMessage) -> str:
		"""extract private sender id metadata for duplicate timestamp grouping."""
		metadata = msg.metadata or {}
		sender = metadata.get(SENDER_USER_ID_KEY)
		if isinstance(sender, str) and sender:
			return sender
		return "user"
