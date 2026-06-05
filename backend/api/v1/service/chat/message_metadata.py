"""private SDK message metadata helpers."""

from __future__ import annotations

from datetime import datetime

from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.types.json import JSONObject


MESSAGE_ID_KEY = "_message_id"
CREATED_AT_KEY = "_created_at"
SENDER_USER_ID_KEY = "_sender_user_id"
STEERING_ENQUEUED_AT_KEY = "steering_enqueued_at"
STEERING_INJECTED_AT_KEY = "steering_injected_at"
STEERING_DROPPED_AT_KEY = "steering_dropped_at"
CLIENT_STEERING_ID_KEY = "client_steering_id"
NEXT_CITATION_INDEX_KEY = "_next_citation_index"
CITATIONS_KEY = "_citations"
ATTACHMENTS_KEY = "attachments"
CITABLE_SOURCES_KEY = "_citable_sources"
CITATIONS_ASSIGNED_KEY = "_citations_assigned"
MODEL_ID_KEY = "_model_id"
E2B_SANDBOX_ID_KEY = "_e2b_sandbox_id"


def get_message_id(msg: SDKMessage) -> str | None:
	"""extract the ORM message ID from SDK message metadata."""
	mid = (msg.metadata or {}).get(MESSAGE_ID_KEY)
	if mid:
		return str(mid)
	return None


def persisted_message_metadata(
	message_id: object,
	created_at: datetime,
	sender_user_id: object | None = None,
) -> JSONObject:
	"""build the private metadata added when loading persisted messages."""
	metadata: JSONObject = {
		MESSAGE_ID_KEY: str(message_id),
		CREATED_AT_KEY: created_at.isoformat(),
	}
	if sender_user_id is not None:
		metadata[SENDER_USER_ID_KEY] = str(sender_user_id)
	return metadata
