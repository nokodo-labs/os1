"""delta (streaming) models.

these are transport-layer wrappers for streaming.
no streaming-related metadata should be stored on domain message models.
"""

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
	"""this chunk of the response being generated."""
	chunk_index: int = Field(default=0, ge=0)
	"""position of this delta in its stream, counted from zero."""
	done: bool = Field(default=False)
	"""whether this response is finished; the message carries no new content."""

	@classmethod
	def done_sentinel(cls, chunk_index: int) -> ChatModelDelta:
		"""build the delta that closes one chat model stream."""
		return cls(message=AssistantMessage(), chunk_index=chunk_index, done=True)


class AgentDelta(Base):
	"""a streamed delta produced by an agent.

	agents can yield:
	- chat model output deltas (AssistantMessage chunks)
	- tool execution results (ToolMessage)
	- a terminal sentinel saying the whole run is over
	"""

	chat: ChatModelDelta | None = Field(default=None)
	"""chat model output, when this delta carries any."""
	tool: ToolMessage | None = Field(default=None)
	"""one tool's result, when this delta carries one."""
	chunk_index: int = Field(default=0, ge=0)
	"""position of this delta within one agent run, counted from zero."""
	done: bool = Field(default=False)
	"""whether the agent run is over; distinct from ``chat.done``, which ends
	one response inside it."""

	@classmethod
	def done_sentinel(cls, chunk_index: int) -> AgentDelta:
		"""build the delta that closes one agent run."""
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
