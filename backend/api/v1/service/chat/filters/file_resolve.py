"""file content resolver filter.

resolves native attachments (images, files) that carry a file_id in
metadata but have no url or base64 data. this filter runs AFTER
attachment_decay so that only active (non-decayed) parts are resolved.

delegates actual file data resolution to the file service.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.v1.service.chat.filters.base import Filter
from api.v1.service.files import resolve_file_data
from nokodo_ai.messages import (
	AssistantMessage as SDKAssistantMessage,
)
from nokodo_ai.messages import (
	FileContent,
	ImageContent,
)
from nokodo_ai.messages import (
	ToolMessage as SDKToolMessage,
)
from nokodo_ai.messages import (
	UserMessage as SDKUserMessage,
)
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from sqlalchemy.ext.asyncio import AsyncSession

	from api.v1.service.auth import Principal
	from api.v1.service.chat.context import AppContext

log = logging.getLogger(__name__)


def _extract_file_id(part: ImageContent | FileContent) -> TypeID | None:
	"""extract file_id from part metadata, if present."""
	meta = part.metadata
	if not meta or not isinstance(meta, dict):
		return None
	fid = meta.get("file_id")
	return TypeID(str(fid)) if fid else None


def _needs_resolution(part: ImageContent | FileContent) -> bool:
	"""check if a content part needs file data populated."""
	if part.url or part.base64:
		return False
	return _extract_file_id(part) is not None


class FileResolveFilter(Filter):
	"""resolves file_id references to actual file data (url or base64).

	this filter is NOT optional and should NOT be in the plugin registry.
	it is always appended by the agent service so it runs last in the
	filter chain. works independently of whether decay or any other
	filter is present.
	"""

	name: str = Field(default="file_resolve")
	description: str = Field(
		default="resolves file_id references to url or base64 for chat model execution"
	)

	async def process(
		self,
		thread: SDKThread,
		app_context: AppContext | None,
	) -> SDKThread:
		"""scan messages for unresolved file parts and populate data."""
		if app_context is None:
			raise ValueError("AppContext is required for FileResolveFilter")

		session = app_context.session
		principal = app_context.principal
		new_messages = list(thread.messages)
		changed = False

		for msg_idx, msg in enumerate(new_messages):
			if isinstance(msg, (SDKUserMessage, SDKAssistantMessage)):
				new_parts = list(msg.content)
				msg_changed = False

				for part_idx, part in enumerate(new_parts):
					resolved = await self._resolve_part(part, session, principal)
					if resolved is not None:
						new_parts[part_idx] = resolved
						msg_changed = True

				if msg_changed:
					new_messages[msg_idx] = msg.model_copy(
						update={"content": new_parts}
					)
					changed = True

			elif isinstance(msg, SDKToolMessage):
				new_atts = list(msg.attachments)
				msg_changed = False

				for att_idx, att in enumerate(new_atts):
					resolved = await self._resolve_part(att, session, principal)
					if resolved is not None:
						new_atts[att_idx] = resolved
						msg_changed = True

				if msg_changed:
					new_messages[msg_idx] = msg.model_copy(
						update={"attachments": new_atts}
					)
					changed = True

		if not changed:
			return thread

		return thread.model_copy(update={"messages": new_messages})

	async def _resolve_part(
		self,
		part: object,
		session: AsyncSession,
		principal: Principal,
	) -> ImageContent | FileContent | None:
		"""resolve a single content part. returns updated part or None if unchanged."""
		if not isinstance(part, (ImageContent, FileContent)):
			return None
		if not _needs_resolution(part):
			return None
		file_id = _extract_file_id(part)
		if not file_id:
			return None
		try:
			b64 = await resolve_file_data(file_id, session, principal=principal)
			if b64:
				return part.model_copy(update={"base64": b64})
			log.warning("file_resolve: no data for file %s", file_id)
		except Exception:
			log.exception("file_resolve: failed to resolve file %s", file_id)
		return None
