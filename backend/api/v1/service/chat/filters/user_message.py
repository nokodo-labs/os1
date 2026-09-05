"""user message filter - decorates user messages for the agent's context.

prepends each user message with its original timestamp and, in multi-human
threads, the sender's name so the agent can follow who said what. runs every
iteration (like all filters) so messages injected mid-run are decorated too.
"""

from datetime import datetime

from pydantic import Field

from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import CREATED_AT_KEY, SENDER_USER_ID_KEY
from api.v1.service.threads import human_roster_labels
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import Message, TextContent, UserContentPart
from nokodo_ai.messages import UserMessage as SDKUserMessage


class UserMessageFilter(Filter):
	"""prefix user messages with their timestamp and (in groups) sender name."""

	name: str = Field(default="user_message")
	description: str = Field(
		default="prepends each user message with its timestamp and, in multi-human"
		" threads, the sender's name"
	)

	_APPLIED_KEY = "_user_message_decorated"

	async def run(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""decorate each user message with timestamp + optional sender label."""
		_ = agent_context
		labels = await self._human_labels(app_context)
		# only attribute speakers when the conversation has multiple humans.
		speaker_labeling = len(labels) >= 2

		thread = state.thread
		new_messages: list[Message] = []
		for msg in thread.messages:
			if not isinstance(msg, SDKUserMessage):
				new_messages.append(msg)
				continue
			if (msg.metadata or {}).get(self._APPLIED_KEY):
				new_messages.append(msg)
				continue

			prefix = self._build_prefix(msg, labels, speaker_labeling)
			if not prefix:
				new_messages.append(msg)
				continue

			new_messages.append(self._apply_prefix(msg, prefix))

		thread.messages = new_messages
		return state

	@staticmethod
	async def _human_labels(app_context: AppContext | None) -> dict[str, str]:
		"""map canonical human roster entries to display labels."""
		if app_context is None or app_context.thread_id is None:
			return {}
		return await human_roster_labels(
			app_context.session,
			app_context.thread_id,
		)

	def _build_prefix(
		self,
		msg: SDKUserMessage,
		labels: dict[str, str],
		speaker_labeling: bool,
	) -> str:
		"""build the inline-metadata prefix for a user message.

		one leading bracket of labeled, pipe-delimited fields, e.g.
		``[from: Alice | at: 2025-06-15 10:30 UTC]``. labels make each field
		unambiguous and the convention extends to future metadata without
		changing the parse shape. fields are omitted when absent (solo chats
		carry only ``at``).
		"""
		fields: list[tuple[str, str]] = []
		if speaker_labeling:
			sender_id = (msg.metadata or {}).get(SENDER_USER_ID_KEY)
			label = labels.get(str(sender_id)) if isinstance(sender_id, str) else None
			if label is not None:
				fields.append(("from", label))
		timestamp = self._resolve_timestamp(msg)
		if timestamp is not None:
			fields.append(("at", timestamp))
		if not fields:
			return ""
		inner = " | ".join(f"{key}: {value}" for key, value in fields)
		return f"[{inner}]"

	def _apply_prefix(self, msg: SDKUserMessage, prefix: str) -> SDKUserMessage:
		"""return a copy of the message with prefix prepended to its first text."""
		new_content: list[UserContentPart] = []
		prefixed = False
		for part in msg.content:
			if not prefixed and isinstance(part, TextContent):
				new_content.append(TextContent(text=f"{prefix} {part.text}"))
				prefixed = True
			else:
				new_content.append(part)
		if not prefixed:
			new_content.insert(0, TextContent(text=prefix))

		new_meta = {**(msg.metadata or {}), self._APPLIED_KEY: True}
		return msg.model_copy(update={"content": new_content, "metadata": new_meta})

	@staticmethod
	def _resolve_timestamp(msg: SDKUserMessage) -> str | None:
		"""extract created_at from private message metadata, or None if absent."""
		metadata = msg.metadata or {}
		iso = metadata.get(CREATED_AT_KEY)
		if not isinstance(iso, str):
			return None
		dt = datetime.fromisoformat(iso)
		return dt.strftime("%Y-%m-%d %H:%M UTC")
