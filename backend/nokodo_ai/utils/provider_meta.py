"""shared helpers for provider-specific tool call ID metadata.

adapters store provider-issued tool call IDs (e.g. openai's "call_xxx",
anthropic's "toolu_xxx") inside message metadata under a namespaced key.
these helpers read/write that structure consistently and support cross-provider
fallback when a conversation switches models mid-stream.
"""

from __future__ import annotations

from ..messages import PROVIDER_DATA_KEY
from ..types.json import JSONObject


def provider_tool_call_metadata(
	*,
	provider: str,
	tool_call_id: str,
) -> JSONObject:
	"""build the metadata dict that stores a provider-issued tool call ID."""
	return {
		PROVIDER_DATA_KEY: {
			provider: {
				"tool_call_id": tool_call_id,
			}
		}
	}


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
	if metadata:
		provider_data = metadata.get(PROVIDER_DATA_KEY)
		if isinstance(provider_data, dict):
			provider_entry = provider_data.get(provider)
			if isinstance(provider_entry, dict):
				tool_call_id = provider_entry.get("tool_call_id")
				if isinstance(tool_call_id, str) and tool_call_id != "":
					return tool_call_id
	return fallback_id
