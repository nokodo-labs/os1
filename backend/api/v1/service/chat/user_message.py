"""user message creation service.

encapsulates the logic for creating a user message during a run,
including input resolution and attachment action event emission.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.file import File as FileORM
from api.models.message import Message as MessageORM
from api.schemas.content import ContentPart, ContentPartAdapter
from api.schemas.message import MessageCreate
from api.schemas.runs import RunInput
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from api.v1.service.events import publish_event
from nokodo_ai.messages import FileContent, ImageContent, TextContent, UserContentPart
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


async def resolve_run_input(
	run_input: RunInput,
	session: AsyncSession,
) -> list[UserContentPart]:
	"""resolve a RunInput into a list of content parts.

	when attachment_ids are present, loads file records from DB and builds
	content parts with proper image/file typing. text is appended last.
	returns an empty list when the input carries neither text nor attachments.
	"""
	parts: list[UserContentPart] = []

	if run_input.attachment_ids:
		ids = [str(fid) for fid in run_input.attachment_ids]
		stmt = select(FileORM).where(FileORM.id.in_(ids))
		result = await session.execute(stmt)
		files_by_id = {str(f.id): f for f in result.scalars().all()}

		for fid in run_input.attachment_ids:
			file_orm = files_by_id.get(str(fid))
			if file_orm is None:
				continue
			mime = file_orm.mime_type or "application/octet-stream"
			metadata: JSONObject = {
				"file_id": str(file_orm.id),
				"attachment_status": "active",
			}
			if mime.startswith("image/"):
				parts.append(
					ImageContent(
						filename=file_orm.filename,
						media_type=mime,
						metadata=metadata,
					)
				)
			else:
				parts.append(
					FileContent(
						filename=file_orm.filename,
						media_type=mime,
						metadata=metadata,
					)
				)

	if run_input.text and run_input.text.strip():
		parts.append(TextContent(text=run_input.text))

	return parts


async def create_run_user_message(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	resolved_input: list[UserContentPart],
	parent_id: TypeID | None,
	run_id: TypeID,
	origin_session_id: str | None = None,
	attachment_actions: Mapping[str, str] | None = None,
) -> MessageORM:
	"""create a user message for a run and emit attachment action events.

	this is the single entry point for creating the user-facing message
	at the start of a persisted run. it handles:
	- validating and converting SDK content parts to API ContentParts
	- persisting the message via thread_service
	- converting attachment actions into lifecycle events for the message
	"""
	msg_content: list[ContentPart] = [
		ContentPartAdapter.validate_python(p.model_dump()) for p in resolved_input
	]

	user_msg = await thread_service.create_message(
		thread_id,
		MessageCreate(
			content=msg_content,
			metadata_={"run_id": run_id},
			parent_id=parent_id,
		),
		session,
		principal=principal,
		origin_session_id=origin_session_id,
	)

	# emit attachment action events scoped to the new user message
	if attachment_actions:
		msg_id_str = str(user_msg.id)
		thread_id_str = str(thread_id)
		user_id_str = str(principal.user.id)
		for fid, action in attachment_actions.items():
			if action == "reveal":
				ev_type = EventType.ATTACHMENT_REVEALED
			elif action == "reference":
				ev_type = EventType.ATTACHMENT_DECAYED
			else:
				continue
			ev = Event(
				scope=EventScope.THREAD,
				scope_id=thread_id_str,
				type=ev_type,
				thread_id=thread_id_str,
				message_id=msg_id_str,
				user_id=user_id_str,
				data={"file_id": fid, "source": "user"},
			)
			await publish_event(session, event=ev)

	return user_msg
