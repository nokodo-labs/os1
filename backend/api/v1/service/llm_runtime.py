"""llm execution helpers (api -> sdk -> api)."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.agent import Agent
from api.models.message import Message as MessageORM
from api.models.message import MessageType as MessageTypeORM
from api.models.model import Model
from api.schemas.content import TextContent
from api.schemas.message import MessageCreate
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import ContentPartAdapter as SDKContentPartAdapter
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolCall as SDKToolCall
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import Usage as SDKUsage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.utils.typeid import TypeID


# ---------------------------------------------------------------------------
# orm <-> sdk conversion (native pydantic)
# ---------------------------------------------------------------------------


def orm_message_to_sdk(orm: MessageORM) -> SDKMessage:
	"""convert an orm message to an sdk message using native pydantic validation.

	The ORM content field is already a list[dict] matching SDK content part schema.
	Tool calls and usage are also stored as dicts matching SDK schemas.
	"""
	# Convert ORM content parts to SDK content parts
	sdk_content = [
		SDKContentPartAdapter.validate_python(part) for part in (orm.content or [])
	]

	match orm.type:
		case MessageTypeORM.USER:
			return SDKUserMessage(
				content=sdk_content,
				metadata=orm.metadata_,
			)
		case MessageTypeORM.SYSTEM:
			return SDKSystemMessage(
				content=sdk_content,
				metadata=orm.metadata_,
			)
		case MessageTypeORM.ASSISTANT:
			tool_calls = [
				SDKToolCall.model_validate(tc) for tc in (orm.tool_calls or [])
			]
			usage = SDKUsage.model_validate(orm.usage) if orm.usage else None
			return SDKAssistantMessage(
				content=sdk_content,
				tool_calls=tool_calls,
				usage=usage,
				metadata=orm.metadata_,
			)
		case MessageTypeORM.TOOL:
			# tool messages store output in first text content; metadata holds call id
			output = ""
			if sdk_content and hasattr(sdk_content[0], "text"):
				output = sdk_content[0].text
			meta = orm.metadata_ or {}
			return SDKToolMessage(
				tool_call_id=meta.get("tool_call_id", ""),
				tool_output=output,
				is_error=meta.get("is_error", False),
				metadata=orm.metadata_,
			)
		case _:
			# Fallback to user message
			return SDKUserMessage(content=sdk_content, metadata=orm.metadata_)


def sdk_message_to_orm_create(
	sdk_msg: SDKMessage,
	*,
	sender_agent_id: TypeID | None = None,
	sender_user_id: TypeID | None = None,
) -> MessageCreate:
	"""convert an sdk message to an orm MessageCreate using native pydantic.

	Content parts are dumped to dicts for JSON storage.
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
			raise ValueError(f"Unknown SDK message role: {sdk_msg.role}")


# Legacy alias for backward compatibility
def sdk_assistant_to_api_create(
	assistant: SDKAssistantMessage,
	*,
	sender_agent_id: TypeID | None = None,
) -> MessageCreate:
	"""convert sdk AssistantMessage to MessageCreate (legacy wrapper)."""
	return sdk_message_to_orm_create(assistant, sender_agent_id=sender_agent_id)


def build_sdk_messages_from_branch(branch: list[MessageORM]) -> list[SDKMessage]:
	"""convert a list of orm messages to sdk messages."""
	return [orm_message_to_sdk(m) for m in branch]


def system_prompt_message(text: str) -> SDKSystemMessage:
	"""create a system message from text."""
	return SDKSystemMessage.from_text(text)


def model_string_from_orm_model(model: Model) -> str:
	"""build the sdk model string from an orm model.

	we map the db provider adapter_type to the sdk provider name by taking the
	first segment (e.g. "openai.responses" -> "openai").

	for now we intentionally ignore adapter variants and let the sdk select its
	default adapter for that provider.
	"""
	provider_key = model.provider.adapter_type.split(".", 1)[0].strip().lower()
	if provider_key == "":
		raise ValueError("provider adapter_type is empty")
	return f"{provider_key}:{model.name}"


async def resolve_model_string_for_run(
	session: AsyncSession,
	*,
	agent_id: TypeID | None = None,
	model_id: TypeID | None = None,
	model: str | None = None,
) -> str:
	"""resolve the sdk model string for a run.

	resolution order:
	- agent_id -> agent.model -> provider
	- model_id -> model -> provider
	- model string passed through as-is
	"""
	if agent_id is not None:
		stmt = (
			select(Agent)
			.options(selectinload(Agent.model).selectinload(Model.provider))
			.where(Agent.id == agent_id)
		)
		result = await session.execute(stmt)
		agent = result.scalars().one_or_none()
		if agent is None:
			raise HTTPException(status_code=404, detail="Agent not found")
		if agent.model is None:
			raise HTTPException(status_code=409, detail="Agent has no model configured")
		return model_string_from_orm_model(agent.model)

	if model_id is not None:
		stmt = (
			select(Model)
			.options(selectinload(Model.provider))
			.where(Model.id == model_id)
		)
		result = await session.execute(stmt)
		m = result.scalars().one_or_none()
		if m is None:
			raise HTTPException(status_code=404, detail="Model not found")
		return model_string_from_orm_model(m)

	if model is None or model.strip() == "":
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="model is required",
		)

	return model
