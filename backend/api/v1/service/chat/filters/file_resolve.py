"""file content resolver filter.

resolves native attachments (images, files) that carry a file_id in
metadata but have no url or base64 data. this filter runs LAST, after the
attachments filter and context compaction, so it only hydrates the media
that actually survives into the model context (active tool-message media).

delegates actual file data resolution to the file service.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.v1.service.chat.filters.base import Filter
from api.v1.service.files import read_file_base64
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	FileContent,
	ImageContent,
)
from nokodo_ai.messages import (
	ToolMessage as SDKToolMessage,
)
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
	"""resolves file_id references to model-ready file data.

	chat messages can carry lightweight image or file parts that reference
	a stored file id without embedding the actual bytes. this filter scans
	user, assistant, and tool messages for unresolved active attachments,
	loads the file through the file service with normal access checks, and
	populates the SDK content part with base64 data when available.

	running this after the attachments filter and context compaction lets it
	hydrate only the media that survives into the model context.
	"""

	name: str = Field(default="file_resolve")
	description: str = Field(
		default=(
			"loads referenced file data so image and file attachments can be "
			"sent to the model"
		)
	)

	async def process(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""scan messages for unresolved file parts and populate data."""
		_ = agent_context
		if app_context is None:
			raise ValueError("AppContext is required for FileResolveFilter")
		thread = state.thread

		session = app_context.session
		principal = app_context.principal
		new_messages = list(thread.messages)
		changed = False

		for msg_idx, msg in enumerate(new_messages):
			# native bytes only ever live on tool messages. the attachments
			# projection has already rewritten any user/assistant media to text
			# references, so hydration is restricted to tool messages.
			if isinstance(msg, SDKToolMessage):
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
			return state

		state.thread = thread.model_copy(update={"messages": new_messages})
		return state

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
			b64 = await read_file_base64(file_id, session, principal=principal)
			if b64:
				return part.model_copy(update={"base64": b64})
			log.warning("file_resolve: no data for file %s", file_id)
		except Exception:
			log.exception("file_resolve: failed to resolve file %s", file_id)
		return None
