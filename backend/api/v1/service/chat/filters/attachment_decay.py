"""attachment decay filter - runtime-computed attachment lifecycle.

scans the thread for native attachments (images, audio, video),
computes turn-based decay, and replaces decayed attachments with
reference markers. the reference manifest is injected into the
system prompt.

state is computed from:
- message chain: attachment positions and tool-based reveals
- persisted events: user reveal/decay actions from current + prior runs
- model capabilities: unsupported modalities are force-decayed

when new decays occur, attachment.decayed events are emitted so the
frontend can update reactively.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import Field

from api.database import async_session_local
from api.models.agent import Agent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.model import Model
from api.settings import settings as app_settings
from api.v1.service import threads as thread_service
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import get_message_id
from api.v1.service.prompt_runtime import SENTINEL_REFERENCED_ATTACHMENTS
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import (
	AssistantMessage as SDKAssistantMessage,
)
from nokodo_ai.messages import (
	ContentPart,
	FileContent,
	ImageContent,
	TextContent,
)
from nokodo_ai.messages import (
	SystemMessage as SDKSystemMessage,
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
	from api.v1.service.chat.context import AppContext

log = logging.getLogger(__name__)

# mime type prefix categories for decay threshold selection

_IMAGE_PREFIXES = ("image/",)
_AUDIO_PREFIXES = ("audio/",)
_VIDEO_PREFIXES = ("video/",)

# map media category -> InputModality value
# attachments whose category isn't in the model's input_modalities
# are force-decayed regardless of turn count
_CATEGORY_TO_MODALITY: dict[str, str] = {
	"image": "images",
	"audio": "audio",
	"video": "video",
}

REVEAL_TOOL_NAME = "reveal_attachment"


@dataclass(slots=True)
class TrackedAttachment:
	"""a native attachment found in the thread."""

	file_id: TypeID
	message_index: int
	part_index: int
	turn: int
	media_type: str | None = None
	filename: str | None = None
	description: str | None = None
	content_type: str = "file"  # "image" or "file"


@dataclass(slots=True)
class RevealRecord:
	"""a reveal_attachment tool call found in the thread."""

	file_ids: list[TypeID] = field(default_factory=list)
	turn: int = 0


def _classify_media(media_type: str | None) -> str:
	"""classify a mime type into image/audio/video/other."""
	if not media_type:
		return "other"
	lower = media_type.lower()
	if any(lower.startswith(p) for p in _IMAGE_PREFIXES):
		return "image"
	if any(lower.startswith(p) for p in _AUDIO_PREFIXES):
		return "audio"
	if any(lower.startswith(p) for p in _VIDEO_PREFIXES):
		return "video"
	return "other"


def _compute_turn_indices(messages: Sequence[object]) -> list[int]:
	"""assign a turn index to each message.

	a turn is one user-to-assistant exchange.
	multiple consecutive user messages = same turn.
	tool messages belong to the turn of the preceding assistant.

	returns a list where result[i] is the turn index for messages[i].
	"""
	turns: list[int] = []
	current_turn = 0
	saw_user_in_turn = False

	for msg in messages:
		if isinstance(msg, SDKSystemMessage):
			turns.append(current_turn)
			continue

		if isinstance(msg, SDKUserMessage):
			if not saw_user_in_turn:
				saw_user_in_turn = True
			turns.append(current_turn)
			continue

		if isinstance(msg, SDKAssistantMessage):
			turns.append(current_turn)
			# turn completes after assistant responds
			if saw_user_in_turn:
				current_turn += 1
				saw_user_in_turn = False
			continue

		if isinstance(msg, SDKToolMessage):
			# tool messages belong to the current turn
			turns.append(current_turn)
			continue

		# unknown message type
		turns.append(current_turn)

	return turns


def _find_attachments(
	messages: Sequence[object],
	turn_indices: list[int],
) -> list[TrackedAttachment]:
	"""find all native attachments across all messages."""
	attachments: list[TrackedAttachment] = []

	for msg_idx, msg in enumerate(messages):
		parts: list[object] = []
		if isinstance(msg, SDKUserMessage):
			parts = list(msg.content)
		elif isinstance(msg, SDKAssistantMessage):
			parts = list(msg.content)
		elif isinstance(msg, SDKToolMessage):
			parts = list(msg.attachments)
		else:
			continue

		for part_idx, part in enumerate(parts):
			if isinstance(part, ImageContent):
				file_id = _extract_file_id(part)
				if file_id:
					attachments.append(
						TrackedAttachment(
							file_id=file_id,
							message_index=msg_idx,
							part_index=part_idx,
							turn=turn_indices[msg_idx],
							media_type=part.media_type,
							filename=part.filename,
							description=_extract_description(part),
							content_type="image",
						)
					)
			elif isinstance(part, FileContent):
				file_id = _extract_file_id(part)
				if file_id:
					attachments.append(
						TrackedAttachment(
							file_id=file_id,
							message_index=msg_idx,
							part_index=part_idx,
							turn=turn_indices[msg_idx],
							media_type=part.media_type,
							filename=part.filename,
							description=_extract_description(part),
							content_type="file",
						)
					)

	return attachments


def _extract_file_id(part: ImageContent | FileContent) -> TypeID | None:
	"""extract file_id from content part metadata."""
	if part.metadata and "file_id" in part.metadata:
		return TypeID(str(part.metadata["file_id"]))
	return None


def _extract_description(part: ImageContent | FileContent) -> str | None:
	"""extract description/summary from content part metadata."""
	if part.metadata and "description" in part.metadata:
		return str(part.metadata["description"])
	return None


def _find_reveals(
	messages: Sequence[object],
	turn_indices: list[int],
) -> list[RevealRecord]:
	"""find all reveal_attachment tool calls in the thread.

	the reveal tool returns success JSON with a 'revealed' key
	containing the list of file_ids. the tool call's existence
	in the thread IS the state.
	"""
	reveals: list[RevealRecord] = []

	for msg_idx, msg in enumerate(messages):
		if not isinstance(msg, SDKToolMessage):
			continue
		# check if this tool message is from a reveal_attachment call
		# the tool name is stored in the preceding assistant's tool_call
		# but we can also check the tool_output for the reveal signature
		if msg.is_error:
			continue
		try:
			output = json.loads(msg.tool_output)
		except (json.JSONDecodeError, TypeError):
			continue
		if not isinstance(output, dict):
			continue
		revealed = output.get("revealed")
		if not isinstance(revealed, list):
			continue
		file_ids = [TypeID(str(fid)) for fid in revealed if fid]
		if file_ids:
			reveals.append(
				RevealRecord(
					file_ids=file_ids,
					turn=turn_indices[msg_idx],
				)
			)

	return reveals


def _get_decay_threshold(
	att: TrackedAttachment,
	image_decay: int,
	audio_decay: int,
	video_decay: int,
) -> int:
	"""get the decay threshold for an attachment based on its media type."""
	category = _classify_media(att.media_type)
	if category == "image":
		return image_decay
	if category == "audio":
		return audio_decay
	if category == "video":
		return video_decay
	# non-native types default to image decay
	return image_decay


def _build_attachment_entry(
	att: TrackedAttachment,
	status: str,
) -> dict[str, object]:
	"""build a JSON entry for an attachment in the inventory manifest."""
	entry: dict[str, object] = {
		"type": att.content_type,
		"id": att.file_id,
		"status": status,
	}
	if att.description:
		entry["summary"] = att.description
	if att.filename:
		entry["filename"] = att.filename
	if att.media_type:
		entry["media_type"] = att.media_type
	return entry


def _format_attachment_manifest(entries: list[dict[str, object]]) -> str:
	"""format the attachment inventory as a system prompt section."""
	lines = [
		"## attachment inventory",
		"",
		"all native attachments in this conversation and their current state:",
		"- **active** - content is included inline in messages. no action needed.",
		"- **reference** - content removed to save context.",
		"  use `reveal_attachment` with the attachment id(s) to restore.",
		"",
		"```json",
		json.dumps(entries, indent=2),
		"```",
	]
	return "\n".join(lines)


async def _fetch_model_input_modalities(
	agent_id: object | None,
) -> set[str] | None:
	"""fetch the model's input_modalities for the given agent.

	returns a set of modality strings (e.g. {"text", "images", "audio"})
	or none if the agent/model can't be resolved.
	uses a fresh session to avoid coupling with the request session.
	"""
	if agent_id is None:
		return None

	try:
		async with async_session_local() as session:
			agent = await session.get(Agent, str(agent_id))
			if agent is None or agent.model_id is None:
				return None
			model = await session.get(Model, agent.model_id)
			if model is None:
				return None
			return set(model.input_modalities)
	except Exception:
		log.debug(
			"could not fetch input modalities for agent %s",
			agent_id,
			exc_info=True,
		)
		return None


def _is_modality_supported(
	att: TrackedAttachment,
	supported: set[str] | None,
) -> bool:
	"""check if an attachment's media category is supported by the model.

	returns true if modalities are unknown (none) - fail open.
	"""
	if supported is None:
		return True
	category = _classify_media(att.media_type)
	modality = _CATEGORY_TO_MODALITY.get(category)
	if modality is None:
		# unknown category (e.g. "other") - allow through
		return True
	return modality in supported


def _extract_message_ids(thread: SDKThread) -> list[TypeID]:
	"""extract message IDs from thread message metadata.

	each sdk message carries its orm id when loaded.
	"""
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
	"""load the latest attachment event state for the message window.

	delegates to thread_service.list_events_for_message_ids with
	attachment-specific event type filtering. for each file_id,
	only the LATEST event determines the current state.

	returns a dict mapping file_id -> "active" | "reference".
	attachments without an event entry are considered active
	by default (handled by the caller).
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

	# latest event per file_id wins (service returns ASC, so iterate reversed)
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


class AttachmentDecayFilter(Filter):
	"""runtime attachment decay filter.

	scans the thread for native attachments, computes turn-based
	decay state from message positions, reveal tool calls,
	and persisted attachment events, then replaces decayed
	attachments with text markers.

	the reference manifest is injected into the system prompt.
	emits attachment.decayed events for frontend reactivity.
	"""

	name: str = Field(default="attachment_decay")
	description: str = Field(
		default="runtime attachment decay - replaces decayed "
		"attachments with reference markers"
	)

	async def process(
		self,
		thread: SDKThread,
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> SDKThread:
		"""replace decayed attachments with prompt references for this turn."""
		_ = agent_context
		if app_context is None:
			raise ValueError("AppContext is required for AttachmentDecayFilter")

		messages = thread.messages

		# locate the system message and check for the injection sentinel.
		# if the admin didn't include {{ referenced_attachments }} in their
		# prompt, the sentinel is absent and we skip all processing.
		system_idx = next(
			(i for i, m in enumerate(messages) if isinstance(m, SDKSystemMessage)),
			None,
		)
		if system_idx is None:
			return thread

		system_msg = messages[system_idx]
		system_text = (
			system_msg.text if isinstance(system_msg, SDKSystemMessage) else ""
		) or ""
		if SENTINEL_REFERENCED_ATTACHMENTS not in system_text:
			return thread

		decay_settings = app_settings.ai.attachments

		if not messages:
			self._inject_sentinel(messages, system_idx, system_text, "")
			return thread

		# compute turn indices for every message
		turn_indices = _compute_turn_indices(messages)
		current_turn = max(turn_indices) if turn_indices else 0

		# find all native attachments
		all_attachments = _find_attachments(messages, turn_indices)
		if not all_attachments:
			self._inject_sentinel(messages, system_idx, system_text, "")
			return thread

		# fetch model's supported input modalities
		supported_modalities = await _fetch_model_input_modalities(
			app_context.agent_id,
		)

		# find all reveal tool calls from message history
		reveals = _find_reveals(messages, turn_indices)

		# load persisted attachment events scoped to the message window
		event_states = await _load_attachment_events(app_context, thread)

		# deduplicate attachments by file_id (keep earliest occurrence)
		seen_file_ids: dict[TypeID, TrackedAttachment] = {}
		for att in all_attachments:
			if att.file_id not in seen_file_ids:
				seen_file_ids[att.file_id] = att

		# compute decay state for each unique attachment
		attachment_entries: list[dict[str, object]] = []
		decayed_file_ids: set[TypeID] = set()

		for file_id, att in seen_file_ids.items():
			ev_state = event_states.get(file_id)
			is_decayed = False

			# latest event says reference - already decayed, skip timer
			if ev_state == "reference":
				is_decayed = True

			# force-decay if the model doesn't support this modality
			elif not _is_modality_supported(att, supported_modalities):
				is_decayed = True

			# latest event says active - skip turn-based decay
			elif ev_state == "active":
				pass

			else:
				# no event - compute turn-based decay
				threshold = _get_decay_threshold(
					att,
					image_decay=decay_settings.image_decay_turns,
					audio_decay=decay_settings.audio_decay_turns,
					video_decay=decay_settings.video_decay_turns,
				)

				# find the latest reveal for this file_id from tool calls
				effective_turn = att.turn
				for reveal in reveals:
					if file_id in reveal.file_ids and reveal.turn > effective_turn:
						effective_turn = reveal.turn
						threshold = decay_settings.reveal_decay_turns

				# check if decayed
				if current_turn - effective_turn >= threshold:
					is_decayed = True

			if is_decayed:
				decayed_file_ids.add(file_id)
				attachment_entries.append(
					_build_attachment_entry(att, status="reference")
				)
			else:
				attachment_entries.append(_build_attachment_entry(att, status="active"))

		# emit decay events only for newly decayed (no prior event)
		prior_decayed = {
			fid for fid, state in event_states.items() if state == "reference"
		}
		newly_decayed = decayed_file_ids - prior_decayed
		if newly_decayed:
			thread_id_str = (
				str(app_context.thread_id) if app_context.thread_id else None
			)
			for fid in newly_decayed:
				att = seen_file_ids[fid]
				event = Event(
					scope=EventScope.THREAD,
					scope_id=thread_id_str,
					type=EventType.ATTACHMENT_DECAYED,
					thread_id=thread_id_str,
					data={
						"file_id": fid,
						"source": "system",
						"media_type": att.media_type,
						"filename": att.filename,
					},
				)
				await app_context.event_emitter(event)

		if not decayed_file_ids:
			manifest = _format_attachment_manifest(attachment_entries)
			self._inject_sentinel(messages, system_idx, system_text, manifest)
			return thread

		# replace decayed attachment content parts with text markers
		for msg in messages:
			if isinstance(msg, SDKUserMessage):
				new_user_content: list[TextContent | ImageContent | FileContent] = []
				for user_part in msg.content:
					if isinstance(user_part, (ImageContent, FileContent)):
						u_fid = _extract_file_id(user_part)
						if u_fid and u_fid in decayed_file_ids:
							u_label = (
								user_part.filename if user_part.filename else u_fid
							)
							new_user_content.append(
								TextContent(
									text=f"[attachment '{u_label}']",
									metadata={"decayed_file_id": u_fid},
								)
							)
							continue
					new_user_content.append(user_part)
				msg.content = new_user_content

			elif isinstance(msg, SDKAssistantMessage):
				new_asst_content: list[ContentPart] = []
				for asst_part in msg.content:
					if isinstance(asst_part, (ImageContent, FileContent)):
						a_fid = _extract_file_id(asst_part)
						if a_fid and a_fid in decayed_file_ids:
							a_label = (
								asst_part.filename if asst_part.filename else a_fid
							)
							new_asst_content.append(
								TextContent(
									text=f"[attachment '{a_label}']",
									metadata={"decayed_file_id": a_fid},
								)
							)
							continue
					new_asst_content.append(asst_part)
				msg.content = new_asst_content

			elif isinstance(msg, SDKToolMessage):
				for t_idx, tool_part in enumerate(msg.attachments):
					if isinstance(tool_part, (ImageContent, FileContent)):
						t_fid = _extract_file_id(tool_part)
						if t_fid and t_fid in decayed_file_ids:
							# tool attachments can't be replaced in-place
							# since the list type is constrained -
							# we clear decayed attachments instead
							msg.attachments[t_idx] = ImageContent(
								url=None,
								base64=None,
								filename=tool_part.filename,
								media_type=tool_part.media_type,
								metadata={
									"decayed_file_id": t_fid,
									"status": "reference",
								},
							)

		manifest = _format_attachment_manifest(attachment_entries)
		self._inject_sentinel(messages, system_idx, system_text, manifest)

		return thread

	@staticmethod
	def _inject_sentinel(
		messages: list[
			SDKSystemMessage | SDKUserMessage | SDKAssistantMessage | SDKToolMessage
		],
		system_idx: int,
		system_text: str,
		content: str,
	) -> None:
		"""replace the filter sentinel in the system message with content."""
		new_text = system_text.replace(SENTINEL_REFERENCED_ATTACHMENTS, content)
		messages[system_idx] = SDKSystemMessage.from_text(new_text)
