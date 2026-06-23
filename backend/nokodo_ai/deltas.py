"""delta (streaming) models.

these are transport-layer wrappers for streaming.
no streaming-related metadata should be stored on domain message models.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from pydantic import Field

from .base import Base
from .messages import AssistantMessage, Message, ToolMessage


class ChatModelDelta(Base):
	"""a streamed delta produced by a chat model.

	- message represents a chunk of data (usually partial assistant output)
	- done is a sentinel indicating the stream for this response is complete

	the provider's run/response id (when the provider exposes one) is
	carried inside ``message.metadata`` under the namespaced provider data
	key - same channel used for tool call ids - and read with
	``nokodo_ai.utils.provider_meta.get_provider_run_id``. callers that
	want to cancel server-side use it with ``ChatModel.cancel_generation``.
	"""

	message: AssistantMessage = Field(default_factory=AssistantMessage)
	chunk_index: int = Field(default=0, ge=0)
	done: bool = Field(default=False)

	@classmethod
	def done_sentinel(cls, chunk_index: int) -> ChatModelDelta:
		return cls(message=AssistantMessage(), chunk_index=chunk_index, done=True)


class AgentDelta(Base):
	"""a streamed delta produced by an agent.

	agents can yield:
	- chat model output deltas (AssistantMessage chunks)
	- tool execution results (ToolMessage)
	"""

	chat: ChatModelDelta | None = Field(default=None)
	tool: ToolMessage | None = Field(default=None)
	chunk_index: int = Field(default=0, ge=0)
	done: bool = Field(default=False)

	@classmethod
	def done_sentinel(cls, chunk_index: int) -> AgentDelta:
		return cls(chunk_index=chunk_index, done=True)


async def stream_chat_model_deltas(
	stream: AsyncIterator[AssistantMessage],
) -> AsyncIterator[ChatModelDelta]:
	"""wrap a chat model message stream in ChatModelDelta objects."""
	chunk_index = 0
	async for message in stream:
		yield ChatModelDelta(message=message, chunk_index=chunk_index)
		chunk_index += 1
	yield ChatModelDelta.done_sentinel(chunk_index=chunk_index)


async def stream_agent_deltas(
	stream: AsyncIterator[Message],
) -> AsyncIterator[AgentDelta]:
	"""wrap an agent message stream in AgentDelta objects."""
	chunk_index = 0
	async for message in stream:
		if isinstance(message, ToolMessage):
			yield AgentDelta(tool=message, chunk_index=chunk_index)
		elif isinstance(message, AssistantMessage):
			yield AgentDelta(
				chat=ChatModelDelta(message=message, chunk_index=0, done=True),
				chunk_index=chunk_index,
			)
		else:
			raise TypeError(f"unsupported agent stream message type: {type(message)}")
		chunk_index += 1
	yield AgentDelta.done_sentinel(chunk_index=chunk_index)
