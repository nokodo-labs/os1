"""shared helpers for provider-specific tool call metadata.

adapters store provider-issued tool call IDs (e.g. openai's "call_xxx",
anthropic's "toolu_xxx") and other adapter-specific data inside message
metadata under a namespaced key. these helpers read/write that structure
consistently and support cross-provider fallback when a conversation
switches models mid-stream.
"""

from __future__ import annotations

from ..messages import PROVIDER_DATA_KEY
from ..types.json import JSONObject, JSONValue


def provider_tool_call_metadata(
	*,
	provider: str,
	tool_call_id: str,
	**extra: JSONValue,
) -> JSONObject:
	"""build metadata dict with a provider-issued tool call ID.

	any additional keyword arguments are stored alongside tool_call_id
	inside the provider-scoped dict, keeping adapter-specific data
	(e.g. google thought_signature) under the same namespace.
	"""
	entry: JSONObject = {"tool_call_id": tool_call_id}
	entry.update(extra)
	return {
		PROVIDER_DATA_KEY: {
			provider: entry,
		}
	}


def get_provider_value(
	*,
	metadata: JSONObject | None,
	provider: str,
	key: str,
) -> JSONValue:
	"""read an arbitrary key from the provider-scoped metadata dict."""
	if not metadata:
		return None
	provider_data = metadata.get(PROVIDER_DATA_KEY)
	if not isinstance(provider_data, dict):
		return None
	provider_entry = provider_data.get(provider)
	if not isinstance(provider_entry, dict):
		return None
	return provider_entry.get(key)


def get_provider_tool_call_id(
	*,
	metadata: JSONObject | None,
	provider: str,
	fallback_id: str | None = None,
) -> str | None:
	"""extract a provider-issued tool call ID from metadata.

	returns the provider-specific ID if present, otherwise falls back to
	``fallback_id`` (typically the sdk's own stable ToolCall.id). this
	enables cross-provider conversation continuity: when the provider key
	is missing because the conversation was started on a different model,
	the sdk ID is used as a consistent substitute.
	"""
	val = get_provider_value(
		metadata=metadata, provider=provider, key="tool_call_id"
	)
	if isinstance(val, str) and val != "":
		return val
	return fallback_id
