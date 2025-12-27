"""base anthropic adapter - shared client infrastructure for anthropic APIs."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from nokodo_ai.adapters.base import BaseApiAdapter


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
			args["base_url"] = self.base_url

		return AsyncAnthropic(**args)
