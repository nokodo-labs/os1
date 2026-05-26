"""message protection helpers for context compaction."""

from __future__ import annotations

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


def protected_indices(
	messages: list[SDKMessage],
	run_id: TypeID | None,
) -> set[int]:
	"""return indices fenced off from prompt-level compression."""
	protected: set[int] = set()
	run_start_index = find_run_start_index(messages, run_id)
	if run_start_index is not None:
		protected.add(run_start_index)
	return protected
