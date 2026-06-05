"""native media projection for the chat context.

native media bytes only ever live on tool messages (file_get fetches and
media generators). this module projects a thread for the model:

- renders all user/assistant media as inline decay markers (never native
  bytes)
- keeps tool-message media native only within its protection window
  (per-modality min-life turns), applies user reveal/decay events and
  dedup, and replaces the rest with inline decay markers
- marks active (in-window) tool messages via metadata so the compaction
  layer can exempt them from prune/summarize

the compaction layer reads the protection marker from message metadata;
this module does not depend on compaction internals, and does no I/O.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from api.settings.settings import AIAttachmentSettings
from api.v1.service.chat.message_metadata import SENDER_USER_ID_KEY
from api.v1.service.files.modalities import classify_media, modality_supported
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
	Message as SDKMessage,
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
from nokodo_ai.utils.typeid import TypeID


log = logging.getLogger(__name__)

# metadata flag set on a tool message that carries HARD-protected native
# media (the read iteration). the compaction layer must never prune or
# summarize these. this is the one-way signal from media -> compaction.
# soft-window media stays native but is NOT marked, so compaction may drop it
# under budget pressure (it is recoverable via file_get).
MEDIA_PROTECTED_METADATA_KEY = "media_protected"

# hard protection window in agent-loop ITERATIONS. the read iteration (the
# first model call that actually sees freshly fetched bytes) is distance 0 and
# is never cut; only it is hard-protected.
_HARD_PROTECTION_ITERATIONS = 1


@dataclass(slots=True)
class _MediaOccurrence:
	"""a single native media part found somewhere in the thread."""

	file_id: TypeID
	message_index: int
	part_index: int
	turn: int
	iteration: int
	on_tool_message: bool
	media_type: str | None = None
	filename: str | None = None
	description: str | None = None
	content_type: str = "file"  # "image" or "file"
	version: str | None = None  # content signature for mutable-file dedup


@dataclass(slots=True)
class MediaProjection:
	"""result of projecting native media for the model context."""

	messages: list[SDKMessage]
	newly_released: set[TypeID] = field(default_factory=set)


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


def _extract_version(part: ImageContent | FileContent) -> str | None:
	"""extract a content signature (file updated_at) for mutable-file dedup."""
	if part.metadata and "updated_at" in part.metadata:
		return str(part.metadata["updated_at"])
	return None


def compute_turn_indices(messages: Sequence[object]) -> list[int]:
	"""assign a turn index to each message.

	a turn belongs to one principal and spans everything that principal did
	before handing the ball back:

	- a user turn is a run of consecutive user messages from one sender; a
	different sender (group threads) starts a new user turn.
	- an agent turn is a whole agent run: every assistant + tool message the
	agent emitted across all of its internal iterations, until the next user
	message. tool messages belong to the agent turn that called them.

	the turn index increments only when the active principal changes, so a
	multi-iteration agent run (assistant -> tool -> assistant -> ...) is a
	single turn, not one per iteration.
	"""
	turns: list[int] = []
	current_turn = -1
	# the principal of the turn in progress: "user", "agent", or none yet.
	current_principal: str | None = None
	# sender of the in-progress user turn, used to split consecutive user
	# messages from different participants in group threads.
	current_user_sender: object | None = None

	for msg in messages:
		if isinstance(msg, SDKSystemMessage):
			# system messages are pinned context, not a conversational turn;
			# fold them into the current turn (or the first turn if leading).
			turns.append(max(current_turn, 0))
			continue

		if isinstance(msg, SDKUserMessage):
			sender = (msg.metadata or {}).get(SENDER_USER_ID_KEY)
			if current_principal != "user" or sender != current_user_sender:
				current_turn += 1
				current_principal = "user"
				current_user_sender = sender
			turns.append(current_turn)
			continue

		# assistant + tool messages are the agent principal
		if current_principal != "agent":
			current_turn += 1
			current_principal = "agent"
			current_user_sender = None
		turns.append(current_turn)

	# a leading agent/system message would leave current_turn at 0 already;
	# clamp any -1 (empty thread) callers never hit, but keep indices >= 0.
	return [max(turn, 0) for turn in turns]


def compute_iteration_indices(messages: Sequence[object]) -> list[int]:
	"""assign an agent-loop iteration index to each message within its turn.

	an agent turn is one agent run; inside it the agent loop restarts once per
	assistant message, and each restart is an iteration. a tool message belongs
	to the iteration of the assistant that called it. the counter resets to 0 at
	the start of every agent turn, so iterations are only comparable within the
	same turn.

	user and system messages are not iterations; they carry the iteration of the
	turn in progress, which media protection never reads (media is native only
	on tool messages).
	"""
	iterations: list[int] = []
	current_principal: str | None = None
	iteration = 0

	for msg in messages:
		if isinstance(msg, SDKSystemMessage):
			iterations.append(iteration)
			continue
		if isinstance(msg, SDKUserMessage):
			if current_principal != "user":
				current_principal = "user"
				iteration = 0
			iterations.append(iteration)
			continue
		# assistant + tool messages are the agent principal
		if current_principal != "agent":
			current_principal = "agent"
			iteration = 0
		if isinstance(msg, SDKAssistantMessage):
			iteration += 1
		iterations.append(iteration)

	return iterations


def _collect_occurrences(
	messages: Sequence[object],
	turn_indices: list[int],
	iteration_indices: list[int],
) -> list[_MediaOccurrence]:
	"""find every native media part across the thread."""
	out: list[_MediaOccurrence] = []
	for msg_idx, msg in enumerate(messages):
		if isinstance(msg, (SDKUserMessage, SDKAssistantMessage)):
			parts: Sequence[object] = msg.content
			on_tool = False
		elif isinstance(msg, SDKToolMessage):
			parts = msg.attachments
			on_tool = True
		else:
			continue

		for part_idx, part in enumerate(parts):
			if not isinstance(part, (ImageContent, FileContent)):
				continue
			file_id = _extract_file_id(part)
			if file_id is None:
				continue
			out.append(
				_MediaOccurrence(
					file_id=file_id,
					message_index=msg_idx,
					part_index=part_idx,
					turn=turn_indices[msg_idx],
					iteration=iteration_indices[msg_idx],
					on_tool_message=on_tool,
					media_type=part.media_type,
					filename=part.filename,
					description=_extract_description(part),
					content_type="image" if isinstance(part, ImageContent) else "file",
					version=_extract_version(part),
				)
			)
	return out


def _protection_iterations(
	media_type: str | None, settings: AIAttachmentSettings
) -> int:
	"""soft protection window (agent-loop iterations) for a media category.

	media survives this many iterations counting the read iteration, all within
	the same agent turn.
	"""
	category = classify_media(media_type)
	if category == "audio":
		return settings.audio_decay_iterations
	if category == "video":
		return settings.video_decay_iterations
	# image + non-native default to the image window
	return settings.image_decay_iterations


# inline marker that replaces released native media bytes. tool-message media
# uses this id-less form because the tool call that produced the result already
# names the file it fetched, so repeating the id would be redundant.
_DECAY_MARKER = "[native media attachment unloaded]"


def _identified_decay_marker(occ: _MediaOccurrence) -> str:
	"""decay marker for natively attached (non-tool) media.

	media attached directly to a user or assistant message is not the result of
	a tool call, so nothing else in the thread names it. unlike the tool-message
	marker, this one carries the file id so the reference is not lost.
	"""
	return f"[native media attachment unloaded: {occ.file_id}]"


def project_attachments(
	messages: Sequence[SDKMessage],
	supported_modalities: set[str] | None,
	settings: AIAttachmentSettings,
) -> MediaProjection:
	"""project native media into a model-ready thread.

	user/assistant media always become inline decay markers. tool-message
	media stays native only for the latest live copy within its protection
	window; everything else is released and its bytes are replaced by an
	inline decay marker.
	"""
	turn_indices = compute_turn_indices(messages)
	iteration_indices = compute_iteration_indices(messages)
	# the agent turn the upcoming model call belongs to. if the thread ends on a
	# user message the next call starts a fresh agent turn that has no live media
	# yet, so nothing from earlier agent turns stays protected.
	current_agent_turn: int | None = None
	current_iteration = 0
	if messages and isinstance(messages[-1], (SDKAssistantMessage, SDKToolMessage)):
		current_agent_turn = turn_indices[-1]
		current_iteration = iteration_indices[-1]
	occurrences = _collect_occurrences(messages, turn_indices, iteration_indices)

	# latest tool occurrence per file_id is the live candidate for release
	# tracking and the dedup fallback.
	latest_tool: dict[TypeID, _MediaOccurrence] = {}
	for occ in occurrences:
		if not occ.on_tool_message:
			continue
		prev = latest_tool.get(occ.file_id)
		if prev is None or occ.message_index >= prev.message_index:
			latest_tool[occ.file_id] = occ

	# a tool occurrence is a true duplicate only when a newer occurrence of the
	# same file carries the same content signature. distinct renditions (the
	# file changed between fetches) are kept so the model does not silently
	# lose a version it may have reasoned about.
	def _is_superseded(occ: _MediaOccurrence) -> bool:
		for other in occurrences:
			if not other.on_tool_message or other.file_id != occ.file_id:
				continue
			if other.message_index <= occ.message_index:
				continue
			if other.version == occ.version:
				return True
		return False

	# decide the native set: media in the CURRENT agent turn, within its
	# iteration window, modality-ok, not superseded. the hard set is the read
	# iteration (distance 0), which compaction must never cut.
	active_indices: dict[TypeID, _MediaOccurrence] = {}
	hard_protected_files: set[TypeID] = set()
	released_indices: set[tuple[int, int]] = set()
	for occ in occurrences:
		if not occ.on_tool_message:
			continue
		in_current_turn = (
			current_agent_turn is not None and occ.turn == current_agent_turn
		)
		distance = current_iteration - occ.iteration
		within_soft = in_current_turn and distance < _protection_iterations(
			occ.media_type, settings
		)
		within_hard = in_current_turn and distance < _HARD_PROTECTION_ITERATIONS
		modality_ok = modality_supported(occ.media_type, supported_modalities)
		keep_native = within_soft and modality_ok and not _is_superseded(occ)
		if keep_native:
			active_indices[occ.file_id] = occ
			if within_hard:
				hard_protected_files.add(occ.file_id)
		else:
			released_indices.add((occ.message_index, occ.part_index))

	# a file is newly released when its latest tool copy exists but is not in
	# the native set (its bytes were just stripped to an inline marker).
	released_files: set[TypeID] = {
		file_id for file_id in latest_tool if file_id not in active_indices
	}

	# transform messages: decay markers for user/assistant, drop released tool
	# attachments (appending a decay marker), keep + protect active tool media.
	new_messages: list[SDKMessage] = []
	occ_by_loc = {(o.message_index, o.part_index): o for o in occurrences}
	for msg_idx, msg in enumerate(messages):
		if isinstance(msg, (SDKUserMessage, SDKAssistantMessage)):
			changed = False
			new_content: list[ContentPart] = []
			for part_idx, part in enumerate(msg.content):
				occ = occ_by_loc.get((msg_idx, part_idx))
				if occ is not None:
					new_content.append(TextContent(text=_identified_decay_marker(occ)))
					changed = True
				else:
					new_content.append(part)
			new_messages.append(
				msg.model_copy(update={"content": new_content}) if changed else msg
			)
			continue

		if isinstance(msg, SDKToolMessage):
			kept: list[ImageContent | FileContent] = []
			any_decayed = False
			has_hard = False
			changed = False
			for part_idx, att in enumerate(msg.attachments):
				if (msg_idx, part_idx) in released_indices:
					changed = True
					any_decayed = True
					continue
				kept.append(att)
				occ = occ_by_loc.get((msg_idx, part_idx))
				if (
					occ is not None
					and occ.file_id in active_indices
					and occ.file_id in hard_protected_files
				):
					has_hard = True
			update: dict[str, object] = {}
			if changed:
				update["attachments"] = kept
				if any_decayed:
					update["tool_output"] = (
						_DECAY_MARKER + "\n" + msg.tool_output
						if msg.tool_output
						else _DECAY_MARKER
					)
			metadata = dict(msg.metadata or {})
			if has_hard:
				if not metadata.get(MEDIA_PROTECTED_METADATA_KEY):
					metadata[MEDIA_PROTECTED_METADATA_KEY] = True
					update["metadata"] = metadata
			elif metadata.pop(MEDIA_PROTECTED_METADATA_KEY, None) is not None:
				update["metadata"] = metadata
			new_messages.append(msg.model_copy(update=update) if update else msg)
			continue

		new_messages.append(msg)

	return MediaProjection(
		messages=new_messages,
		newly_released=released_files,
	)
