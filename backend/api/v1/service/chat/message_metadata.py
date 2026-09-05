"""private SDK message metadata helpers."""

from collections.abc import Mapping
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
ORIGINATED_RESOURCES_KEY = "_originated_resources"
CITATIONS_ASSIGNED_KEY = "_citations_assigned"
MODEL_ID_KEY = "_model_id"
E2B_SANDBOX_ID_KEY = "_e2b_sandbox_id"


# keys the ORM→SDK fold injects on top of the persisted metadata column
# (identity mirrors + citations/attachments column projections); the SDK→ORM
# unfold strips exactly this set so they never double-write into the column.
ROUND_TRIP_IDENTITY_KEYS: frozenset[str] = frozenset(
	{MESSAGE_ID_KEY, CREATED_AT_KEY, SENDER_USER_ID_KEY}
)
COLUMN_PROJECTED_KEYS: frozenset[str] = frozenset(
	{CITATIONS_KEY, ATTACHMENTS_KEY, ORIGINATED_RESOURCES_KEY}
)
FOLDED_METADATA_KEYS: frozenset[str] = ROUND_TRIP_IDENTITY_KEYS | COLUMN_PROJECTED_KEYS


def to_persisted_metadata(sdk_metadata: JSONObject | None) -> JSONObject:
	"""SDK→ORM metadata unfold: drop fold-injected keys, carry the rest.

	the result is still in the flat, ``_``-prefixed SDK shape; use
	``split_sdk_metadata`` to get the two halves the column stores.
	"""
	if not sdk_metadata:
		return {}
	return {k: v for k, v in sdk_metadata.items() if k not in FOLDED_METADATA_KEYS}


def split_sdk_metadata(
	sdk_metadata: JSONObject | None,
) -> tuple[JSONObject, JSONObject]:
	"""split flat SDK metadata into the (public, private) halves.

	inverse of ``Message._sdk_metadata``. private keys are returned de-prefixed.
	"""
	public: JSONObject = {}
	private: JSONObject = {}
	for key, value in (sdk_metadata or {}).items():
		if key.startswith("_"):
			private[key[1:]] = value
		else:
			public[key] = value
	return public, private


def strip_private_sdk_metadata(value: object) -> object:
	"""copy a streamed SDK payload, dropping `_`-prefixed keys from every
	nested metadata object."""
	if isinstance(value, Mapping):
		payload: dict[str, object] = {}
		for key, item in value.items():
			key_str = str(key)
			if key_str == "metadata" and isinstance(item, Mapping):
				payload[key_str] = {
					str(meta_key): meta_value
					for meta_key, meta_value in item.items()
					if not str(meta_key).startswith("_")
				}
			else:
				payload[key_str] = strip_private_sdk_metadata(item)
		return payload
	if isinstance(value, list):
		return [strip_private_sdk_metadata(item) for item in value]
	return value


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
