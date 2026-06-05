"""attachments filter - native media projection + reference resolution.

projects native media (in-window tool-message bytes and active-media
protection) and resolves every message's attachment references the same way:
resolvable refs (the agent has a tool to open them) collapse into a hydrated
``[attachments: [...]]`` block, and the rest are inlined directly so the model
still sees them when no resolver tool is available.

the rendering prepends to the message: ahead of content parts for messages
that have them, or onto ``tool_output`` (text) and ``attachments`` (native
media) for tool messages, which have no content parts.

media projection lives in ``context_compaction.media``; reference hydration
is handled inline in this module. this filter performs the I/O and wiring.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.thread_summary import SummaryPurpose
from api.settings import settings as app_settings
from api.v1.service.auth import Principal
from api.v1.service.calendar.calendars import get_calendar
from api.v1.service.calendar.events import get_calendar_event
from api.v1.service.chat.context_compaction.media import project_attachments
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import ATTACHMENTS_KEY
from api.v1.service.chat.models import fetch_agent_input_modalities
from api.v1.service.files.modalities import classify_media, modality_supported
from api.v1.service.files.service import get_file
from api.v1.service.notes import get_note
from api.v1.service.projects import get_project
from api.v1.service.reminders.core import get_reminder
from api.v1.service.reminders.lists import get_reminder_list
from api.v1.service.threads.core import get_thread
from api.v1.service.threads.summaries import list_thread_summaries
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ContentPart, FileContent, ImageContent, TextContent
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

log = logging.getLogger(__name__)

_PREVIEW_LIMIT = 200
_TITLE_LIMIT = 120


def _title(text: str | None) -> str | None:
	"""collapse whitespace and truncate a title. ids are never truncated."""
	if not text:
		return None
	collapsed = " ".join(text.split())
	if not collapsed:
		return None
	return collapsed[:_TITLE_LIMIT]


def _preview(text: str | None) -> str | None:
	"""collapse whitespace and truncate a description preview."""
	if not text:
		return None
	collapsed = " ".join(text.split())
	if not collapsed:
		return None
	return collapsed[:_PREVIEW_LIMIT]


async def _load_display(
	ref_type: str,
	ref_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> tuple[str | None, str | None]:
	"""load (title, description) for a single reference, or raise on access."""
	if ref_type == "file":
		f = await get_file(ref_id, session, principal)
		return (f.filename or "file", _preview(f.description))
	if ref_type == "note":
		n = await get_note(ref_id, session, principal)
		return (n.title or None, _preview(n.content))
	if ref_type == "thread":
		t = await get_thread(ref_id, session, principal)
		return (t.title or None, None)
	if ref_type == "project":
		p = await get_project(ref_id, session, principal)
		return (p.name or None, _preview(p.description))
	if ref_type == "reminder":
		r = await get_reminder(ref_id, session, principal)
		return (r.title or None, _preview(r.description))
	if ref_type == "reminder_list":
		rl = await get_reminder_list(ref_id, session, principal)
		return (rl.name or None, _preview(rl.description))
	if ref_type == "calendar_event":
		e = await get_calendar_event(ref_id, session, principal)
		return (e.title or None, _preview(e.description))
	if ref_type == "calendar":
		c = await get_calendar(ref_id, session, principal)
		return (c.name or None, _preview(c.description))
	return (None, None)


async def resolve_attachment_refs(
	refs: Sequence[object],
	session: AsyncSession,
	principal: Principal,
) -> list[JSONObject]:
	"""resolve raw attachment references into display entries."""
	resolved: list[JSONObject] = []
	for ref in refs:
		if not isinstance(ref, dict):
			continue
		mapping = cast("dict[str, object]", ref)
		ref_type = mapping.get("type")
		raw_id = mapping.get("id")
		if not isinstance(ref_type, str) or not isinstance(raw_id, str):
			continue
		entry: JSONObject = {"type": ref_type, "id": raw_id}
		try:
			typed_id = TypeID(raw_id)
			title, description = await _load_display(
				ref_type, typed_id, session, principal
			)
		except (HTTPException, ValueError):
			resolved.append(entry)
			continue
		title_text = _title(title)
		if title_text:
			entry["title"] = title_text
		if description:
			entry["description"] = description
		resolved.append(entry)
	return resolved


_RESOLUTION_TOOL: dict[str, str] = {
	"file": "file_get",
	"note": "note_get",
	"thread": "chat_get",
	"project": "project_get",
	"reminder": "reminder_get",
	"reminder_list": "reminder_get",
	"calendar_event": "calendar_event_get",
	"calendar": "calendar_event_get",
}


def _ref_is_resolvable(ref_type: str, available_tools: set[str]) -> bool:
	"""whether the agent has the tool needed to resolve this ref type."""
	tool = _RESOLUTION_TOOL.get(ref_type)
	return tool is not None and tool in available_tools


async def _inline_file_parts(
	ref_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	supported: set[str] | None,
) -> list[ContentPart]:
	"""inline a file natively when the model supports the media, else as text."""
	f = await get_file(ref_id, session, principal)
	mime = f.mime_type or "application/octet-stream"
	category = classify_media(mime)
	if category in ("image", "audio", "video") and modality_supported(mime, supported):
		metadata: JSONObject = {"file_id": str(f.id)}
		if category == "image":
			return [
				ImageContent(filename=f.filename, media_type=mime, metadata=metadata)
			]
		return [FileContent(filename=f.filename, media_type=mime, metadata=metadata)]
	label = f.filename or str(ref_id)
	body = f" {f.description}" if f.description else ""
	return [TextContent(text=f"[attachment file '{label}' ({mime}):{body}]")]


async def _catalog_entry(
	ref_type: str,
	ref_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> tuple[str | None, str | None, list[str] | None]:
	"""return (title, summary, tags) for inlining a non-file ref."""
	if ref_type == "note":
		n = await get_note(ref_id, session, principal)
		return (n.title or None, n.content or None, None)
	if ref_type == "thread":
		t = await get_thread(ref_id, session, principal)
		summary: str | None = None
		try:
			summaries = await list_thread_summaries(
				ref_id, session, principal, purpose=SummaryPurpose.CATALOG
			)
		except (HTTPException, ValueError):
			summaries = []
		if summaries:
			summary = summaries[0].content or None
		tags = list(t.tags or [])
		return (t.title or None, summary, tags or None)
	if ref_type == "project":
		p = await get_project(ref_id, session, principal)
		return (p.name or None, p.description or None, None)
	if ref_type == "reminder":
		r = await get_reminder(ref_id, session, principal)
		return (r.title or None, r.description or None, None)
	if ref_type == "reminder_list":
		rl = await get_reminder_list(ref_id, session, principal)
		return (rl.name or None, rl.description or None, None)
	if ref_type == "calendar_event":
		e = await get_calendar_event(ref_id, session, principal)
		return (e.title or None, e.description or None, None)
	if ref_type == "calendar":
		c = await get_calendar(ref_id, session, principal)
		return (c.name or None, c.description or None, None)
	return (None, None, None)


async def _inline_ref_parts(
	ref: object,
	session: AsyncSession,
	principal: Principal,
	supported: set[str] | None,
) -> list[ContentPart]:
	"""resolve one unresolvable ref into inline content parts."""
	if not isinstance(ref, dict):
		return []
	mapping = cast("dict[str, object]", ref)
	ref_type = mapping.get("type")
	raw_id = mapping.get("id")
	if not isinstance(ref_type, str) or not isinstance(raw_id, str):
		return []
	try:
		ref_id = TypeID(raw_id)
		if ref_type == "file":
			return await _inline_file_parts(ref_id, session, principal, supported)
		title, summary, tags = await _catalog_entry(
			ref_type, ref_id, session, principal
		)
	except (HTTPException, ValueError):
		return []
	if not title and not summary and not tags:
		return []
	label = title or raw_id
	tags_str = f" tags={tags}" if tags else ""
	body = f": {summary}" if summary else ""
	return [TextContent(text=f"[attachment {ref_type} '{label}'{tags_str}{body}]")]


async def _render_refs(
	refs: Sequence[object],
	available_tools: set[str],
	session: AsyncSession,
	principal: Principal,
	supported: set[str] | None,
) -> list[ContentPart]:
	"""render a message's attachment refs into prependable content parts.

	resolvable refs (the agent has a tool to open them) collapse into a single
	hydrated ``[attachments: [...]]`` block; the rest are inlined directly so the
	model still sees them when no resolver tool is available.
	"""
	resolvable: list[object] = []
	unresolvable: list[object] = []
	for ref in refs:
		if not isinstance(ref, dict):
			continue
		mapping = cast("dict[str, object]", ref)
		ref_type = mapping.get("type")
		if isinstance(ref_type, str) and _ref_is_resolvable(ref_type, available_tools):
			resolvable.append(ref)
		else:
			unresolvable.append(ref)
	parts: list[ContentPart] = []
	if resolvable:
		entries = await resolve_attachment_refs(resolvable, session, principal)
		if entries:
			block = "[attachments: " + json.dumps(entries, ensure_ascii=False) + "]"
			parts.append(TextContent(text=block))
	for ref in unresolvable:
		parts.extend(await _inline_ref_parts(ref, session, principal, supported))
	return parts


def _prepend_to_tool_message(
	msg: SDKToolMessage, parts: Sequence[ContentPart]
) -> SDKToolMessage:
	"""prepend rendered attachment parts to a tool message.

	tool messages have no content parts, so text renderings (the ref block and
	inline catalog) prepend to ``tool_output`` while native media joins
	``attachments`` (hydrated later by file_resolve).
	"""
	texts = [part.text for part in parts if isinstance(part, TextContent)]
	media: list[ImageContent | FileContent] = [
		part for part in parts if isinstance(part, (ImageContent, FileContent))
	]
	update: dict[str, object] = {}
	if texts:
		update["tool_output"] = "\n".join([*texts, msg.tool_output])
	if media:
		update["attachments"] = [*msg.attachments, *media]
	if not update:
		return msg
	return msg.model_copy(update=update)


class AttachmentsFilter(Filter):
	"""native media projection + attachment-reference resolution.

	projects native media (in-window tool-message bytes and active-media
	protection) and renders every message's attachment references in place:
	resolvable refs become a hydrated ``[attachments: [...]]`` block, the rest
	inline directly. the rendering prepends to content parts, or to
	``tool_output``/``attachments`` for tool messages.
	"""

	name: str = Field(default="attachments")
	description: str = Field(
		default="native media projection and attachment-reference rendering"
	)

	async def process(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""project native media and render attachment references."""
		_ = agent_context
		if app_context is None:
			raise ValueError("AppContext is required for AttachmentsFilter")

		thread = state.thread
		messages = thread.messages
		session = app_context.session
		principal = app_context.principal

		supported = await fetch_agent_input_modalities(
			app_context.agent_id, app_context.session
		)

		projection = project_attachments(
			messages,
			supported,
			app_settings.ai.attachments,
		)

		new_messages = list(projection.messages)
		available_tools = {tool.name for tool in state.tools}
		for idx, msg in enumerate(new_messages):
			refs = (msg.metadata or {}).get(ATTACHMENTS_KEY)
			if not isinstance(refs, list) or not refs:
				continue
			rendered = await _render_refs(
				refs, available_tools, session, principal, supported
			)
			if not rendered:
				continue
			# tool messages have no content parts; everything else prepends ahead
			# of its own content.
			if isinstance(msg, SDKToolMessage):
				new_messages[idx] = _prepend_to_tool_message(msg, rendered)
			else:
				new_messages[idx] = msg.model_copy(
					update={"content": [*rendered, *msg.content]}
				)
		state.thread = thread.model_copy(update={"messages": new_messages})

		return state
