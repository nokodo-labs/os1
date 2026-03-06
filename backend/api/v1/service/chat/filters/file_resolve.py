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
	FileContent,
	ImageContent,
)
from nokodo_ai.messages import (
	UserMessage as SDKUserMessage,
)
from nokodo_ai.threads import Thread as SDKThread


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

log = logging.getLogger(__name__)


def _extract_file_id(part: ImageContent | FileContent) -> str | None:
	"""extract file_id from part metadata, if present."""
	meta = part.metadata
	if not meta or not isinstance(meta, dict):
		return None
	fid = meta.get("file_id")
	return str(fid) if fid else None


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
		"""scan user messages for unresolved file parts and populate data."""
		if app_context is None:
			raise ValueError("AppContext is required for FileResolveFilter")

		session = app_context.session
		principal = app_context.principal
		new_messages = list(thread.messages)
		changed = False

		for msg_idx, msg in enumerate(new_messages):
			if not isinstance(msg, SDKUserMessage):
				continue

			new_parts = list(msg.content)
			msg_changed = False

			for part_idx, part in enumerate(new_parts):
				if not isinstance(part, (ImageContent, FileContent)):
					continue
				if not _needs_resolution(part):
					continue

				file_id = _extract_file_id(part)
				if not file_id:
					continue

				try:
					b64 = await resolve_file_data(file_id, session, principal=principal)
					if b64:
						new_parts[part_idx] = part.model_copy(update={"base64": b64})
						msg_changed = True
					else:
						log.warning("file_resolve: no data for file %s", file_id)
				except Exception:
					log.exception("file_resolve: failed to resolve file %s", file_id)

			if msg_changed:
				new_messages[msg_idx] = msg.model_copy(update={"content": new_parts})
				changed = True

		if not changed:
			return thread

		return thread.model_copy(update={"messages": new_messages})
