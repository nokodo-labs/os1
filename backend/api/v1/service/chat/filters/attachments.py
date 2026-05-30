"""attachments filter - native media projection.

renders user/assistant media as references, keeps in-window tool-message
media native, builds the inventory manifest, and marks active media via
metadata so the compaction layer exempts it from prune/summarize.

projection logic lives in ``context_compaction.media``; this filter only
performs the I/O (model modalities, attachment events) and wiring.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.settings import settings as app_settings
from api.v1.service import threads as thread_service
from api.v1.service.chat.context_compaction.media import project_media
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import get_message_id
from api.v1.service.chat.models import fetch_agent_input_modalities
from api.v1.service.prompts import SENTINEL_REFERENCED_ATTACHMENTS
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

log = logging.getLogger(__name__)


def _extract_message_ids(thread: SDKThread) -> list[TypeID]:
	"""extract persisted message IDs from thread message metadata."""
	ids: list[TypeID] = []
	for msg in thread.messages:
		mid = get_message_id(msg)
		if mid:
			ids.append(TypeID(mid))
	return ids


async def _load_attachment_events(
	app_context: AppContext,
	thread: SDKThread,
) -> dict[TypeID, str]:
	"""load the latest user/agent attachment state for the message window.

	returns file_id -> "active" | "reference"; latest event per file wins.
	"""
	if app_context.thread_id is None:
		return {}
	message_ids = _extract_message_ids(thread)
	if not message_ids:
		return {}
	events = await thread_service.list_events_for_message_ids(
		app_context.thread_id,
		message_ids,
		app_context.session,
		principal=app_context.principal,
		event_types=[
			EventType.ATTACHMENT_REVEALED,
			EventType.ATTACHMENT_DECAYED,
		],
	)
	states: dict[TypeID, str] = {}
	for ev in reversed(events):
		data = ev.data or {}
		file_id = data.get("file_id")
		if not file_id:
			continue
		fid = TypeID(str(file_id))
		if fid in states:
			continue
		if ev.type == EventType.ATTACHMENT_REVEALED:
			states[fid] = "active"
		elif ev.type == EventType.ATTACHMENT_DECAYED:
			states[fid] = "reference"
	return states


class AttachmentsFilter(Filter):
	"""native media projection.

	renders user/assistant media as references, keeps in-window tool-message
	media native (dedup + min-life + user events), builds the inventory
	manifest, and marks active media so the compaction layer exempts it.
	emits attachment.decayed events when media is newly released.
	"""

	name: str = Field(default="attachments")
	description: str = Field(
		default="native media projection - references, inventory, and protection"
	)

	async def process(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""project native media for the model context."""
		_ = agent_context
		if app_context is None:
			raise ValueError("AppContext is required for AttachmentsFilter")

		thread = state.thread
		messages = thread.messages

		system_idx = next(
			(i for i, m in enumerate(messages) if isinstance(m, SDKSystemMessage)),
			None,
		)
		if system_idx is None:
			return state
		system_msg = messages[system_idx]
		system_text = (
			system_msg.text if isinstance(system_msg, SDKSystemMessage) else ""
		) or ""
		# the attachment system is gated on the admin prompt sentinel.
		if SENTINEL_REFERENCED_ATTACHMENTS not in system_text:
			return state

		supported = await fetch_agent_input_modalities(
			app_context.agent_id, app_context.session
		)
		event_states = await _load_attachment_events(app_context, thread)

		projection = project_media(
			messages,
			supported,
			event_states,
			app_settings.ai.attachments,
		)

		new_messages = list(projection.messages)
		new_messages[system_idx] = SDKSystemMessage.from_text(
			system_text.replace(SENTINEL_REFERENCED_ATTACHMENTS, projection.manifest)
		)
		state.thread = thread.model_copy(update={"messages": new_messages})

		# emit release events for newly released media (frontend reactivity)
		if projection.newly_released and app_context.thread_id is not None:
			thread_id_str = str(app_context.thread_id)
			for fid in projection.newly_released:
				occ = projection.released_meta.get(fid)
				event = Event(
					scope=EventScope.THREAD,
					scope_id=thread_id_str,
					type=EventType.ATTACHMENT_DECAYED,
					thread_id=thread_id_str,
					data={
						"file_id": str(fid),
						"source": "system",
						"media_type": occ.media_type if occ else None,
						"filename": occ.filename if occ else None,
					},
				)
				await app_context.event_emitter(event)

		return state
