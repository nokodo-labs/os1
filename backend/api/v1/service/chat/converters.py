"""sdk -> orm message conversions for persistence."""

from __future__ import annotations

from api.models.message import MessageType as MessageTypeORM
from api.schemas.content import TextContent
from api.schemas.message import MessageCreate
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.utils.typeid import TypeID


def sdk_message_to_orm_create(
	sdk_msg: SDKMessage,
	*,
	sender_agent_id: TypeID | None = None,
	sender_user_id: TypeID | None = None,
) -> MessageCreate:
	"""convert an sdk message to an orm MessageCreate for persistence.

	content parts are dumped to dicts for json storage.
	"""
	match sdk_msg.role:
		case "user":
			assert isinstance(sdk_msg, SDKUserMessage)
			return MessageCreate(
				type=MessageTypeORM.USER,
				content=[part.model_dump() for part in sdk_msg.content],
				sender_user_id=sender_user_id,
			)
		case "system":
			assert isinstance(sdk_msg, SDKSystemMessage)
			return MessageCreate(
				type=MessageTypeORM.SYSTEM,
				content=[part.model_dump() for part in sdk_msg.content],
			)
		case "assistant":
			assert isinstance(sdk_msg, SDKAssistantMessage)
			return MessageCreate(
				type=MessageTypeORM.ASSISTANT,
				content=[part.model_dump() for part in sdk_msg.content],
				tool_calls=[tc.model_dump() for tc in sdk_msg.tool_calls],
				usage=sdk_msg.usage.model_dump() if sdk_msg.usage else None,
				sender_agent_id=sender_agent_id,
			)
		case "tool":
			assert isinstance(sdk_msg, SDKToolMessage)
			return MessageCreate(
				type=MessageTypeORM.TOOL,
				content=[TextContent(text=sdk_msg.tool_output).model_dump()],
				metadata_={
					"tool_call_id": sdk_msg.tool_call_id,
					"is_error": sdk_msg.is_error,
				},
			)
		case _:
			raise ValueError(f"unknown sdk message role: {sdk_msg.role}")


def system_prompt_message(text: str) -> SDKSystemMessage:
	"""create a system message from text."""
	return SDKSystemMessage.from_text(text)
