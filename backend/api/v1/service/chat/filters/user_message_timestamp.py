"""user message timestamp filter - prepends created_at to user messages."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from nokodo_ai.messages import TextContent
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread


class UserMessageTimestampFilter(Filter):
	"""prepends the original created_at timestamp to each user message."""

	name: str = Field(default="user_message_timestamp")
	description: str = Field(
		default="prepends the original UTC date and time to every user message"
	)

	_APPLIED_KEY = "_timestamped"

	async def process(
		self,
		thread: SDKThread,
		app_context: AppContext | None,
	) -> SDKThread:
		new_messages = []
		for msg in thread.messages:
			if not isinstance(msg, SDKUserMessage):
				new_messages.append(msg)
				continue

			if (msg.metadata or {}).get(self._APPLIED_KEY):
				new_messages.append(msg)
				continue

			timestamp = self._resolve_timestamp(msg)
			if timestamp is None:
				new_messages.append(msg)
				continue

			prefix = f"[{timestamp}] "

			new_content = []
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

		thread.messages = new_messages
		return thread

	@staticmethod
	def _resolve_timestamp(msg: SDKUserMessage) -> str | None:
		"""extract created_at from message metadata, or None if absent."""
		iso = (msg.metadata or {}).get("created_at")
		if not isinstance(iso, str):
			return None
		dt = datetime.fromisoformat(iso)
		return dt.strftime("%Y-%m-%d %H:%M UTC")
