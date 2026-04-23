"""shared helpers for provider-specific tool call metadata.

adapters store provider-issued tool call IDs (e.g. openai's "call_xxx",
anthropic's "toolu_xxx") and other adapter-specific data inside message
metadata under a namespaced key. these helpers read/write that structure
consistently and support cross-provider fallback when a conversation
switches models mid-stream.
"""

from __future__ import annotations

import logging
from time import time

from ..messages import PROVIDER_DATA_KEY, AssistantMessage
from ..types.json import JSONObject, JSONValue


logger = logging.getLogger(__name__)


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


def provider_run_metadata(*, provider: str, run_id: str) -> JSONObject:
	"""build metadata dict carrying a provider-issued run/response id.

	lives under the same namespaced channel as tool call ids. adapters
	that get a server-side id for the in-flight generation should attach
	this to the first ``AssistantMessage`` chunk they yield.
	"""
	return {
		PROVIDER_DATA_KEY: {
			provider: {"run_id": run_id},
		}
	}


def get_provider_run_id(
	metadata: JSONObject | None,
) -> tuple[str, str] | None:
	"""extract (provider, run_id) from message metadata, if present.

	returns the first provider entry that carries a non-empty ``run_id``
	string. callers use the returned pair to call
	``ChatModel.cancel_generation`` with the right id.
	"""
	if not metadata:
		return None
	provider_data = metadata.get(PROVIDER_DATA_KEY)
	if not isinstance(provider_data, dict):
		return None
	for provider, entry in provider_data.items():
		if not isinstance(entry, dict):
			continue
		run_id = entry.get("run_id")
		if isinstance(run_id, str) and run_id:
			return provider, run_id
	return None


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
	val = get_provider_value(metadata=metadata, provider=provider, key="tool_call_id")
	if isinstance(val, str) and val != "":
		return val
	return fallback_id


class RunIdTracker:
	"""tracks the provider run_id during a streaming generation.

	adapters instantiate this with their provider name and call
	``observe()`` whenever they encounter a run_id in a streaming event.
	if the id is new or changed, ``observe()`` returns an
	``AssistantMessage`` metadata chunk to yield; otherwise ``None``.

	a mid-stream id change is logged as a warning (should never happen
	under normal operation).
	"""

	def __init__(self, provider: str) -> None:
		self.provider = provider
		self._run_id: str | None = None

	@property
	def run_id(self) -> str | None:
		return self._run_id

	def observe(self, run_id: str) -> AssistantMessage | None:
		"""record a run_id; return a metadata chunk if new or changed."""
		if not run_id:
			return None

		now = time()
		if self._run_id is None:
			self._run_id = run_id
			return AssistantMessage(
				metadata=provider_run_metadata(provider=self.provider, run_id=run_id),
				created_at=now,
				updated_at=now,
			)
		if run_id != self._run_id:
			logger.warning(
				"provider run_id changed mid-stream: %s -> %s",
				self._run_id,
				run_id,
			)
			self._run_id = run_id
			return AssistantMessage(
				metadata=provider_run_metadata(provider=self.provider, run_id=run_id),
				created_at=now,
				updated_at=now,
			)
		return None
