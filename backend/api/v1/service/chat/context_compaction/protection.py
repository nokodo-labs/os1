"""message protection helpers for context compaction."""

from __future__ import annotations

from api.v1.service.chat.context_compaction.media import (
	MEDIA_PROTECTED_METADATA_KEY,
)
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.utils.typeid import TypeID


_RUN_ID_METADATA_KEY = "run_id"


def find_run_start_index(
	messages: list[SDKMessage],
	run_id: TypeID | None,
) -> int | None:
	"""find the current run's starting user message index."""
	if run_id is None:
		return None
	run_id_text = str(run_id)
	for index, message in enumerate(messages):
		metadata = message.metadata or {}
		if (
			message.role == "user"
			and str(metadata.get(_RUN_ID_METADATA_KEY)) == run_id_text
		):
			return index
	return None


def find_media_protected_index(messages: list[SDKMessage]) -> int | None:
	"""find the earliest message carrying active (in-window) native media.

	the attachments filter marks these messages; compaction must not prune or
	summarize across them so the model keeps the bytes it was told it can see.
	"""
	for index, message in enumerate(messages):
		metadata = message.metadata or {}
		if metadata.get(MEDIA_PROTECTED_METADATA_KEY):
			return index
	return None


def protected_floor_index(
	messages: list[SDKMessage],
	run_id: TypeID | None,
) -> int | None:
	"""lowest index that compaction must not cross.

	the floor is the earliest of the current run start and any active media
	message. returns none when nothing is protected (callers treat that as
	"summarize/prune up to the end of history").

	note: this scalar is NOT the prune/summarize floor. prune and summarize
	fence off the full SET from `protected_indices`, so gaps between protected
	islands stay compressible. this minimum is only used to bound summary reuse
	(a summary may not span past the earliest protected message).
	"""
	candidates = [
		index
		for index in (
			find_run_start_index(messages, run_id),
			find_media_protected_index(messages),
		)
		if index is not None
	]
	return min(candidates) if candidates else None


def protected_indices(
	messages: list[SDKMessage],
	run_id: TypeID | None,
) -> set[int]:
	"""return indices fenced off from prompt-level compression."""
	protected: set[int] = set()
	run_start_index = find_run_start_index(messages, run_id)
	if run_start_index is not None:
		protected.add(run_start_index)
	for index, message in enumerate(messages):
		metadata = message.metadata or {}
		if metadata.get(MEDIA_PROTECTED_METADATA_KEY):
			protected.add(index)
	return protected
