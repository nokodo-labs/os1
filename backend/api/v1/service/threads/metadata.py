"""service helpers for threads and messages."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import (
	session_scope,
)
from api.models.access_rule import AccessLevel
from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.thread import ThreadUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import fetch_acl_metadata, require_thread_access
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.threads.core import update_thread
from api.v1.service.threads.search import THREAD_SPEC
from api.v1.service.vectorize import (
	vectorize_resource,
)
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class _ThreadMetadataOut(BaseModel):
	"""structured output schema for thread metadata generation."""

	title: str = Field(
		description="emoji followed by 1-3 lowercase words.",
		max_length=50,
		examples=[
			"🧠 brainstorm new app features",
			"📚 research quantum computing",
			"🫂 help with friends",
		],
	)
	tags: list[str] = Field(
		description="short lowercase tags",
		max_length=15,
	)


def thread_metadata_missing(thread: Thread) -> bool:
	"""whether mandatory thread title or tags still need to be generated."""
	return (thread.title or "").strip() == "" or not thread.tags


async def generate_thread_metadata(
	thread_id: TypeID,
	principal: Principal,
	session: AsyncSession | None = None,
	replace: bool = False,
	create_event: bool = True,
	origin_session_id: str | None = None,
) -> Thread:
	"""generate thread metadata (title/tags) and persist via update_thread.

	when *replace* is false, only fills missing fields.
	when *session* is ``None`` (fire-and-forget), an independent session is
	created automatically.

	raises on failure - never returns ``None``.
	"""
	async with session_scope(session) as session:
		# auth: caller must have admin-level access on the thread
		await require_thread_access(
			thread_id,
			session,
			principal,
			required_level=AccessLevel.ADMIN,
		)

		chat_model = await resolve_task_chat_model(session, "thread_metadata")

		thread = await session.get(
			Thread,
			thread_id,
			options=[
				selectinload(Thread.messages),
				selectinload(Thread.projects),
			],
		)
		if not thread or thread.deleted_at or thread.is_temporary:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="thread not found or not eligible for metadata generation",
			)

		existing_title = (thread.title or "").strip()
		has_title = existing_title != ""
		has_tags = bool(thread.tags) and len(thread.tags) > 0
		should_update_title = replace or not has_title
		should_update_tags = replace or not has_tags
		if not should_update_title and not should_update_tags:
			return thread

		messages = sorted(thread.messages or [], key=lambda m: m.created_at)

		# build turns: each (user_msg | None, assistant_msg) pair
		turns: list[tuple[Message | None, Message]] = []
		pending_user: Message | None = None
		for m in messages:
			if m.type == MessageType.USER:
				pending_user = m
			elif m.type == MessageType.ASSISTANT:
				turns.append((pending_user, m))
				pending_user = None

		if not turns:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="cannot generate metadata: no assistant message in thread",
			)

		# first 2 turns + latest 4 turns when thread has > 2, else use all
		if len(turns) > 2:
			indices = sorted(
				set(range(min(2, len(turns))))
				| set(range(max(0, len(turns) - 4), len(turns)))
			)
			selected_turns = [turns[i] for i in indices]
		else:
			selected_turns = turns

		turn_data = [
			{
				"user": t[0].text_content[:500] if t[0] else "",
				"assistant": t[1].text_content[:500],
			}
			for t in selected_turns
		]

		sdk_thread = SDKThread(
			messages=[
				SDKSystemMessage.from_text(
					"given the following chat history turns, generate thread metadata."
				),
				SDKUserMessage.from_text(json.dumps(turn_data)),
			]
		)

		data = await run_chat_model_json_schema(
			chat_model,
			thread=sdk_thread,
			json_schema=_ThreadMetadataOut.model_json_schema(),
			purpose="thread_metadata",
		)
		out = _ThreadMetadataOut.model_validate(data)

		desired_title = out.title.strip().lower() or None
		desired_tags = out.tags[:6]

		update_fields: dict[str, object] = {}
		if (
			should_update_title
			and desired_title is not None
			and desired_title != thread.title
		):
			update_fields["title"] = desired_title
		if should_update_tags and desired_tags != (thread.tags or []):
			update_fields["tags"] = desired_tags
		if not update_fields:
			return thread
		update_in = ThreadUpdate.model_validate(update_fields)

		result = await update_thread(
			thread_id,
			update_in,
			session,
			principal=principal,
			create_event=create_event,
			origin_session_id=origin_session_id,
			update_activity=False,
		)

		# index thread with new metadata (title/tags + full message text for BM25)
		await session.refresh(thread, attribute_names=["messages"])
		await vectorize_resource(
			spec=THREAD_SPEC,
			resource=thread,
			session=session,
			extra_metadata=await fetch_acl_metadata(
				str(thread.id), ResourceType.THREAD, session
			),
		)

		return result
