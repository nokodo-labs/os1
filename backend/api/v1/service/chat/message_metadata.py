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


# keys the ORM→SDK fold injects on top of the persisted metadata column
# (identity mirrors + citations/attachments column projections); the SDK→ORM
# unfold strips exactly this set so they never double-write into the column.
ROUND_TRIP_IDENTITY_KEYS: frozenset[str] = frozenset(
	{MESSAGE_ID_KEY, CREATED_AT_KEY, SENDER_USER_ID_KEY}
)
COLUMN_PROJECTED_KEYS: frozenset[str] = frozenset({CITATIONS_KEY, ATTACHMENTS_KEY})
FOLDED_METADATA_KEYS: frozenset[str] = ROUND_TRIP_IDENTITY_KEYS | COLUMN_PROJECTED_KEYS


def to_persisted_metadata(sdk_metadata: JSONObject | None) -> JSONObject:
	"""SDK→ORM metadata unfold: drop fold-injected keys, carry the rest."""
	if not sdk_metadata:
		return {}
	return {k: v for k, v in sdk_metadata.items() if k not in FOLDED_METADATA_KEYS}


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
