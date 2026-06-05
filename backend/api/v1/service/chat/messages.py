"""message boundary helpers - orm<->sdk conversion and sse serialization.

owns the conversions between persisted ORM messages and the runtime SDK
thread used by the agent loop:

- ``load_sdk_thread`` loads a thread branch and converts it to an SDK thread,
	enriching each message with its persisted metadata, citation index, and
	attachment refs so downstream filters need no extra ORM lookups.
- ``build_message_create`` performs the reverse (streamed SDK message ->
	``MessageCreate``) for persistence.
- ``inject_system_instructions`` renders and prepends an agent's system prompt.
"""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent as AgentORM
from api.models.message import Message as MessageORM
from api.schemas.message import (
	Citation,
	MessageCreate,
	ResourceAttachment,
)
from api.schemas.runs import ClientContext, RunInput
from api.settings import settings
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.chat.filters.citation_index import resolve_assistant_citations
from api.v1.service.chat.message_metadata import (
	ATTACHMENTS_KEY,
	CITATIONS_KEY,
	CLIENT_STEERING_ID_KEY,
	MESSAGE_ID_KEY,
	MODEL_ID_KEY,
	NEXT_CITATION_INDEX_KEY,
	SENDER_USER_ID_KEY,
	STEERING_ENQUEUED_AT_KEY,
	persisted_message_metadata,
)
from api.v1.service.prompts import render_agent_instructions
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import TextContent as SDKTextContent
from nokodo_ai.messages import UserContentPart as SDKUserContentPart
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.typeid import TypeID


_INVISIBLE_PAYLOAD_CHAR_LIMIT = 256
_INVISIBLE_PAYLOAD_BYTE_LIMIT = 1_024
_INVISIBLE_PAYLOAD_RE = re.compile(
	"[\u200b-\u200d\u2060\ufeff\ufe00-\ufe0f\U000e0000-\U000e007f\U000e0100-\U000e01ef]"
)


def _has_invisible_payload(text: str) -> bool:
	char_count = 0
	byte_count = 0
	for match in _INVISIBLE_PAYLOAD_RE.finditer(text):
		char_count += 1
		if char_count > _INVISIBLE_PAYLOAD_CHAR_LIMIT:
			return True
		byte_count += 4 if ord(match[0]) > 0xFFFF else 3
		if byte_count > _INVISIBLE_PAYLOAD_BYTE_LIMIT:
			return True
	return False


def validate_run_input(run_input: RunInput | None) -> None:
	"""validate run input limits and reject suspicious invisible payloads."""
	text = run_input.text if run_input else None
	if text is None:
		return
	if _has_invisible_payload(text):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="input text contains too many invisible unicode characters",
		)
	max_chars = settings.limits.max_chat_input_chars
	if max_chars is None or len(text) <= max_chars:
		return
	raise HTTPException(
		status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
		detail=f"input text exceeds max_chat_input_chars ({max_chars})",
	)


def build_run_input_sdk_user_message(run_input: RunInput) -> SDKUserMessage:
	"""build an SDK user message from RunInput text and attachment refs."""
	parts: list[SDKUserContentPart] = []
	if run_input.text and run_input.text.strip():
		parts.append(SDKTextContent(text=run_input.text))
	metadata: JSONObject = {}
	if run_input.attachments:
		metadata[ATTACHMENTS_KEY] = [
			attachment.model_dump(mode="json") for attachment in run_input.attachments
		]
	return SDKUserMessage(content=parts, metadata=(metadata or None))


def build_steering_sdk_message(
	user_msg: MessageORM,
	principal_user_id: TypeID,
	enqueued_at: datetime,
	client_steering_id: str | None,
) -> SDKUserMessage:
	"""build the queued steering SDK message from a persisted user message."""
	sdk_metadata: JSONObject = {
		MESSAGE_ID_KEY: str(user_msg.id),
		SENDER_USER_ID_KEY: str(principal_user_id),
		STEERING_ENQUEUED_AT_KEY: enqueued_at.isoformat(),
	}
	if client_steering_id is not None:
		sdk_metadata[CLIENT_STEERING_ID_KEY] = client_steering_id
	if user_msg.attachments:
		sdk_metadata[ATTACHMENTS_KEY] = [
			ResourceAttachment.model_validate(a).model_dump(mode="json")
			for a in user_msg.attachments
		]

	base_sdk = orm_message_to_sdk_message(
		user_msg,
		include_persisted_metadata=False,
		include_citations=False,
		include_attachments=False,
		include_existing_metadata=False,
	)
	assert isinstance(base_sdk, SDKUserMessage)
	return base_sdk.model_copy(update={"metadata": sdk_metadata})


def orm_message_to_sdk_message(
	msg: MessageORM,
	include_persisted_metadata: bool = True,
	include_citations: bool = True,
	include_attachments: bool = True,
	include_existing_metadata: bool = True,
) -> SDKMessage:
	"""convert one persisted ORM message into an SDK message."""
	sdk = msg.to_sdk()
	metadata: JSONObject = dict(sdk.metadata or {}) if include_existing_metadata else {}

	if include_persisted_metadata:
		metadata.update(
			persisted_message_metadata(msg.id, msg.created_at, msg.sender_user_id)
		)

	if include_citations and msg.type == "assistant" and msg.citations:
		citation_payload: list[JSONValue] = []
		for citation in msg.citations:
			citation_payload.append(citation)
		metadata[CITATIONS_KEY] = citation_payload

	if include_attachments and msg.attachments:
		metadata[ATTACHMENTS_KEY] = [
			ResourceAttachment.model_validate(a).model_dump(mode="json")
			for a in msg.attachments
		]

	if not metadata:
		return sdk.model_copy(update={"metadata": None})
	return sdk.model_copy(update={"metadata": metadata})


async def load_sdk_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	parent_id: TypeID | None = None,
) -> tuple[SDKThread, TypeID | None]:
	"""load a thread's message branch and convert to an SDK thread.

	uses an optimized single-pass load (no redundant thread queries)
	with a recursive CTE for branch walking.

	each sdk message carries its orm id
	so downstream filters can identify messages without needing a
	separate lookup.

	returns (sdk_thread, current_message_id) so callers can derive
	the parent id for new messages without a separate query.
	"""
	thread_orm, branch_orm = await thread_service.load_thread_with_branch(
		thread_id,
		session,
		principal=principal,
		parent_id=parent_id,
	)
	head_id = thread_orm.current_message_id

	sdk_messages = [orm_message_to_sdk_message(m) for m in branch_orm]

	sdk_thread = SDKThread(
		created_at=thread_orm.created_at,
		messages=sdk_messages,
		metadata=thread_orm.metadata_ or {},
	)
	return sdk_thread, head_id


def _build_message_create(
	sdk_msg: SDKMessage,
	sender_agent_id: TypeID | None,
	run_id: TypeID,
	citations: list[Citation],
	model_id: str | None,
) -> MessageCreate:
	"""build a MessageCreate from a streamed sdk message for persistence.

	owns the sdk->orm conversion for runs: lifts attachment refs out of
	private metadata into the attachments column and resolves assistant
	citations from the runtime citation list.
	"""
	create_in = MessageCreate.from_sdk_message(
		sdk_msg,
		sender_agent_id=sender_agent_id,
	)
	# lift attachment refs into the column and drop the metadata copy so it
	# is not persisted twice (from_sdk_message copies tool metadata verbatim).
	refs = (sdk_msg.metadata or {}).get(ATTACHMENTS_KEY)
	if isinstance(refs, list):
		create_in.attachments = [ResourceAttachment.model_validate(r) for r in refs]
	create_in.metadata.pop(ATTACHMENTS_KEY, None)
	if isinstance(sdk_msg, SDKAssistantMessage):
		text = ""
		for part in sdk_msg.content or []:
			if isinstance(part, SDKTextContent) and part.text:
				text += part.text
		resolved = resolve_assistant_citations(text, citations)
		if resolved:
			create_in.citations = resolved
		# stamp the running index so future runs can pick up without
		# loading the full branch.
		if citations:
			create_in.metadata[NEXT_CITATION_INDEX_KEY] = citations[-1].index + 1
	create_in.metadata["run_id"] = run_id
	if model_id:
		create_in.metadata[MODEL_ID_KEY] = model_id
	return create_in


async def persist_sdk_message(
	thread_id: TypeID,
	sdk_msg: SDKMessage,
	session: AsyncSession,
	principal: Principal,
	sender_agent_id: TypeID | None,
	run_id: TypeID,
	citations: list[Citation],
	model_id: str | None,
	message_id: TypeID | None,
	parent_id: TypeID | None,
	origin_session_id: str | None,
) -> MessageORM:
	"""persist one SDK message through the threads message service."""
	create_in = _build_message_create(
		sdk_msg,
		sender_agent_id=sender_agent_id,
		run_id=run_id,
		citations=citations,
		model_id=model_id,
	)
	create_in.parent_id = parent_id
	return await thread_service.create_message(
		thread_id=thread_id,
		message_in=create_in,
		session=session,
		principal=principal,
		message_id=message_id,
		origin_session_id=origin_session_id,
	)


async def inject_system_instructions(
	agent_orm: AgentORM,
	thread: SDKThread,
	session: AsyncSession,
	principal: Principal | None = None,
	client_context: ClientContext | None = None,
) -> SDKThread:
	"""inject an agent's rendered system instructions at the start of a thread."""
	if not agent_orm.system_prompt:
		return thread

	user = principal.user if principal else None
	rendered = await render_agent_instructions(
		session,
		text=agent_orm.system_prompt,
		user=user,
		client_context=client_context,
	)
	if not rendered:
		return thread

	system_msg = SDKSystemMessage.from_text(rendered)
	return thread.model_copy(update={"messages": [system_msg, *thread.messages]})
