"""the domain input `create_message` persists.

deliberately not a pydantic model: a dataclass cannot be bound as a request
body, so fields with no wire representation (the private metadata half) are
unreachable from HTTP by construction.
"""

from dataclasses import dataclass, field

from api.models.message import MessageType
from api.schemas.message import (
	Citation,
	ContentPart,
	ContentPartAdapter,
	MessageCreate,
	MessageMention,
	MessageSplice,
	ResourceAttachment,
	TextContent,
)
from api.v1.service.chat.message_metadata import split_sdk_metadata
from nokodo_ai.messages import BaseContentPart as SDKContentPart
from nokodo_ai.messages import FinishReason
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.types.sentinels import MISSING, MissingType
from nokodo_ai.utils.typeid import TypeID


def _storage_parts(parts: list[SDKContentPart]) -> list[ContentPart]:
	"""convert SDK content parts for DB storage.

	inline data (base64/url) is stripped from parts carrying a file_id: the
	bytes live in File storage, so only the reference is persisted.
	"""
	result: list[ContentPart] = []
	for part in parts:
		payload = part.model_dump()
		if isinstance(payload, dict) and (payload.get("metadata") or {}).get("file_id"):
			payload.pop("base64", None)
			payload.pop("url", None)
		result.append(ContentPartAdapter.validate_python(payload))
	return result


@dataclass(slots=True)
class MessageDraft:
	"""everything needed to persist one message into a thread."""

	type: MessageType = MessageType.USER
	"""which kind of message row this becomes."""
	content: list[ContentPart] = field(default_factory=list)
	"""the message body, already normalized to storage parts."""
	metadata: JSONObject = field(default_factory=dict)
	"""metadata anyone reading the message can see."""
	private_metadata: JSONObject = field(default_factory=dict)
	"""backend-owned metadata, unreachable from the wire by construction."""
	attachments: list[ResourceAttachment] = field(default_factory=list)
	"""resources shared into the thread by this message."""
	citations: list[Citation] = field(default_factory=list)
	"""sources this message cites, in citation order."""
	tool_call_id: str | None = None
	"""the tool call this message answers, for a tool result."""
	is_error: bool | None = None
	"""whether a tool result reports a failure."""
	tool_calls: list[dict[str, object]] = field(default_factory=list)
	"""tool calls an assistant message is requesting."""
	finish_reason: FinishReason | None = None
	"""why generation stopped, for an assistant message."""
	usage: dict[str, object] | None = None
	"""provider token counts for an assistant message."""
	splice: MessageSplice | MissingType = MISSING
	"""explicit placement; MISSING lets the write derive it."""
	reply_to_message_id: TypeID | None = None
	"""what this message answers - semantic, and separate from placement."""
	mentions: list[MessageMention] = field(default_factory=list)
	"""subjects addressed here, which is what can invoke an agent."""
	task_id: TypeID | None = None
	"""the task this message belongs to, when one produced it."""
	sender_agent_id: TypeID | None = None
	"""the agent that authored this, set only for generated messages."""
	sender_user_id: TypeID | None = None
	"""the person that authored this."""

	@classmethod
	def from_request(cls, message_in: MessageCreate) -> MessageDraft:
		"""build a draft from a client-submitted payload.

		copies every field ``MessageCreate`` declares; the private half is
		left empty, since the wire cannot express it.
		"""
		# the schema's validator already normalized content to parts.
		return cls(
			type=message_in.type,
			content=list(message_in.content),
			metadata=message_in.metadata,
			attachments=message_in.attachments,
			citations=message_in.citations,
			tool_call_id=message_in.tool_call_id,
			is_error=message_in.is_error,
			tool_calls=[
				tool_call.model_dump(mode="json", exclude_none=True)
				for tool_call in message_in.tool_calls
			],
			usage=(
				message_in.usage.model_dump(mode="json")
				if message_in.usage is not None
				else None
			),
			splice=message_in.splice if message_in.splice is not None else MISSING,
			reply_to_message_id=message_in.reply_to_message_id,
			mentions=list(message_in.mentions),
			task_id=message_in.task_id,
			sender_user_id=message_in.sender_user_id,
		)

	@classmethod
	def from_sdk_message(
		cls,
		sdk_msg: SDKMessage,
		sender_agent_id: TypeID | None = None,
	) -> MessageDraft:
		"""build a draft from a message the agent loop produced.

		``sender_user_id`` is always left unset: an SDK message is authored by
		the model, not a user.
		"""
		public, private = split_sdk_metadata(sdk_msg.metadata)
		match sdk_msg.role:
			case "user":
				return cls(
					type=MessageType.USER,
					content=_storage_parts(list(sdk_msg.content)),
					metadata=public,
					private_metadata=private,
					sender_agent_id=sender_agent_id,
				)
			case "system":
				return cls(
					type=MessageType.SYSTEM,
					content=_storage_parts(list(sdk_msg.content)),
					metadata=public,
					private_metadata=private,
					sender_agent_id=sender_agent_id,
				)
			case "assistant":
				return cls(
					type=MessageType.ASSISTANT,
					content=_storage_parts(list(sdk_msg.content)),
					tool_calls=[
						tc.model_dump(mode="json") for tc in sdk_msg.tool_calls
					],
					finish_reason=sdk_msg.finish_reason,
					usage=(
						sdk_msg.usage.model_dump(mode="json") if sdk_msg.usage else None
					),
					metadata=public,
					private_metadata=private,
					sender_agent_id=sender_agent_id,
				)
			case "tool":
				parts: list[ContentPart] = [TextContent(text=sdk_msg.tool_output)]
				if sdk_msg.attachments:
					parts.extend(_storage_parts(list(sdk_msg.attachments)))
				return cls(
					type=MessageType.TOOL,
					content=parts,
					tool_call_id=sdk_msg.tool_call_id,
					is_error=sdk_msg.is_error,
					metadata=public,
					private_metadata=private,
					sender_agent_id=sender_agent_id,
				)
			case _:
				raise ValueError(f"unknown sdk message role: {sdk_msg.role}")
