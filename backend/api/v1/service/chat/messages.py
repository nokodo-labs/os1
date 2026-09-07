"""message boundary helpers - orm<->sdk conversion and sse serialization.

owns the conversions between persisted ORM messages and the runtime SDK
thread used by the agent loop:

- ``load_sdk_thread`` loads a thread branch and converts it to an SDK thread,
	enriching each message with its persisted metadata, citation index, and
	attachment refs so downstream filters need no extra ORM lookups.
- ``prepare_generated_message`` performs the reverse conversion for thread
	persistence.
- ``inject_system_instructions`` renders and prepends an agent's system prompt.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent as AgentORM
from api.models.message import Message as MessageORM
from api.schemas.message import (
	Citation,
	FileContent,
	ImageContent,
	MessageCreate,
	ResourceAttachment,
	TextContent,
)
from api.schemas.runs import ClientContext
from api.settings import settings
from api.v1.service.authentication import Principal
from api.v1.service.chat.filters.citation_index import resolve_assistant_citations
from api.v1.service.chat.message_metadata import (
	ATTACHMENTS_KEY,
	CITATIONS_KEY,
	CLIENT_STEERING_ID_KEY,
	MESSAGE_ID_KEY,
	MODEL_ID_KEY,
	NEXT_CITATION_INDEX_KEY,
	ORIGINATED_RESOURCES_KEY,
	SENDER_USER_ID_KEY,
	STEERING_ENQUEUED_AT_KEY,
	persisted_message_metadata,
	to_persisted_metadata,
)
from api.v1.service.prompts import render_agent_instructions
from api.v1.service.threads import MessageDraft, load_thread_with_branch
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import FileContent as SDKFileContent
from nokodo_ai.messages import ImageContent as SDKImageContent
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import TextContent as SDKTextContent
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.types.sentinels import MISSING, MissingType
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


def run_input_text(run_input: MessageCreate | None) -> str | None:
	"""the plain text a run's input message carries, if any."""
	if run_input is None:
		return None
	parts = [
		part.text
		for part in run_input.content
		if isinstance(part, TextContent) and part.text
	]
	return " ".join(parts) if parts else None


def validate_message_input(message_input: MessageCreate | None) -> None:
	"""validate message input limits and reject suspicious invisible payloads."""
	text = run_input_text(message_input)
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


def build_run_input_sdk_user_message(run_input: MessageCreate) -> SDKUserMessage:
	"""build an SDK user message from a run's input message."""
	parts: list[SDKTextContent | SDKImageContent | SDKFileContent] = []
	for part in run_input.content:
		match part:
			case TextContent():
				parts.append(
					SDKTextContent.model_validate(part.model_dump(mode="json"))
				)
			case ImageContent():
				parts.append(
					SDKImageContent.model_validate(part.model_dump(mode="json"))
				)
			case FileContent():
				parts.append(
					SDKFileContent.model_validate(part.model_dump(mode="json"))
				)
			case _:
				raise ValueError("unsupported run input content")
	metadata: JSONObject = dict(run_input.metadata)
	if run_input.attachments:
		metadata[ATTACHMENTS_KEY] = [
			attachment.model_dump(mode="json") for attachment in run_input.attachments
		]
	if run_input.originated_resources:
		metadata[ORIGINATED_RESOURCES_KEY] = [
			resource.model_dump(mode="json")
			for resource in run_input.originated_resources
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
	if not isinstance(base_sdk, SDKUserMessage):
		raise ValueError("steering input must resolve to a user message")
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
	parent_id: TypeID | None | MissingType = MISSING,
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
	thread_orm, branch_orm = await load_thread_with_branch(
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
		metadata=thread_orm.public_metadata,
	)
	return sdk_thread, head_id


async def load_sdk_thread_before_message(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> tuple[SDKThread, TypeID | None]:
	"""load conversation context ending immediately before one message."""
	thread_orm, branch_orm = await load_thread_with_branch(
		thread_id,
		session,
		principal=principal,
		parent_id=message_id,
	)
	if not branch_orm or branch_orm[-1].id != message_id:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="message is no longer on its conversation path",
		)
	context = branch_orm[:-1]
	predecessor_id = context[-1].id if context else None
	return (
		SDKThread(
			created_at=thread_orm.created_at,
			messages=[orm_message_to_sdk_message(message) for message in context],
			metadata=thread_orm.public_metadata,
		),
		predecessor_id,
	)


@dataclass(frozen=True, slots=True)
class PreparedGeneratedMessage:
	"""domain input derived from one generated SDK message."""

	draft: MessageDraft
	originated_resources: list[ResourceAttachment]


def prepare_generated_message(
	sdk_msg: SDKMessage,
	sender_agent_id: TypeID | None,
	run_id: TypeID,
	citations: list[Citation],
	model_id: str | None,
) -> PreparedGeneratedMessage:
	"""convert a generated SDK message into thread-write input.

	SDK→ORM boundary: strips the fold-injected keys BEFORE the public/private
	split, lifts attachment refs into the attachments column, and routes
	backend-owned stamps into the private half. real metadata rides through.
	"""
	# unfold first: the folded keys are `_`-prefixed, so filtering after the
	# split would let identity mirrors reach the private half of the column.
	persisted = to_persisted_metadata(sdk_msg.metadata)
	draft = MessageDraft.from_sdk_message(
		sdk_msg.model_copy(update={"metadata": persisted}),
		sender_agent_id=sender_agent_id,
	)
	# lift attachment refs into the column
	refs = (sdk_msg.metadata or {}).get(ATTACHMENTS_KEY)
	if isinstance(refs, list):
		draft.attachments = [ResourceAttachment.model_validate(r) for r in refs]
	if isinstance(sdk_msg, SDKAssistantMessage):
		text = ""
		for part in sdk_msg.content or []:
			if isinstance(part, SDKTextContent) and part.text:
				text += part.text
		resolved = resolve_assistant_citations(text, citations)
		if resolved:
			draft.citations = resolved
		# stamp the running index so future runs can pick up without
		# loading the full branch.
		if citations:
			draft.private_metadata[NEXT_CITATION_INDEX_KEY.removeprefix("_")] = (
				citations[-1].index + 1
			)
	draft.metadata["run_id"] = str(run_id)
	if model_id:
		draft.private_metadata[MODEL_ID_KEY.removeprefix("_")] = model_id
	refs = (sdk_msg.metadata or {}).get(ORIGINATED_RESOURCES_KEY)
	originated_resources = (
		[ResourceAttachment.model_validate(ref) for ref in refs]
		if isinstance(refs, list)
		else []
	)
	return PreparedGeneratedMessage(
		draft=draft,
		originated_resources=originated_resources,
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

	user = principal.subject if principal else None
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
