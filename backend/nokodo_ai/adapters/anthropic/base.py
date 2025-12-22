"""base anthropic adapter - shared client infrastructure for anthropic APIs."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from nokodo_ai.adapters.base import BaseAdapter


class BaseAnthropicAdapter(BaseAdapter):
	"""shared infrastructure for all anthropic adapters.

	provides:
	- anthropic client initialization
	- api_key management
	- timeout and retry settings
	"""

	def __init__(
		self,
		*,
		api_key: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize anthropic adapter.

		args:
			api_key: anthropic API key (defaults to ANTHROPIC_API_KEY env var)
			timeout: request timeout in seconds
		"""
		self.api_key = api_key
		self.timeout = timeout
		# client will be lazily initialized when needed
		self._client: AsyncAnthropic | None = None

	def _get_client(self) -> AsyncAnthropic:
		"""get (or create) an AsyncAnthropic client."""
		if self._client is None:
			if self.api_key is None:
				self._client = AsyncAnthropic(timeout=self.timeout)
			else:
				self._client = AsyncAnthropic(
					api_key=self.api_key, timeout=self.timeout
				)
		return self._client

	@property
	def client(self) -> AsyncAnthropic:
		"""get the AsyncAnthropic client."""
		return self._get_client()
