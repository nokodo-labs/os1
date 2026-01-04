"""base anthropic adapter - shared client infrastructure for anthropic APIs."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from ..base import BaseApiAdapter


def _normalize_anthropic_base_url(base_url: str) -> str:
	url = base_url.strip().rstrip("/")
	if url.endswith("/v1"):
		return url[:-3]
	return url


class BaseAnthropicAdapter(BaseApiAdapter[AsyncAnthropic]):
	"""shared infrastructure for all anthropic adapters.

	provides:
	- anthropic client initialization
	- api_key management
	- timeout and retry settings
	"""

	def _get_client(self) -> AsyncAnthropic:
		"""get (or create) an AsyncAnthropic client."""
		args = {}
		args["timeout"] = self.timeout
		if self.api_key is not None:
			args["api_key"] = self.api_key
		if self.base_url is not None:
			args["base_url"] = _normalize_anthropic_base_url(self.base_url)

		return AsyncAnthropic(**args)
