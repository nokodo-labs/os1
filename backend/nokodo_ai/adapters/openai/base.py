"""base openai adapter - shared client infrastructure for openai APIs."""

from __future__ import annotations

from openai import AsyncOpenAI

from nokodo_ai.adapters.base import BaseAdapter


class BaseOpenAIAdapter(BaseAdapter):
	"""shared infrastructure for all openai adapters.

	provides:
	- openai client initialization
	- api_key management
	- base_url configuration (for proxies/custom endpoints)
	- timeout and retry settings
	"""

	def __init__(
		self,
		*,
		api_key: str | None = None,
		base_url: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize openai adapter.

		args:
			api_key: openai API key (defaults to OPENAI_API_KEY env var)
			base_url: custom base URL for proxies or alternative endpoints
			timeout: request timeout in seconds
		"""
		self.api_key = api_key
		self.base_url = base_url
		self.timeout = timeout
		# client will be lazily initialized when needed
		self._client: AsyncOpenAI | None = None

	def _get_client(self) -> AsyncOpenAI:
		"""get (or create) an AsyncOpenAI client."""
		if self._client is None:
			if self.api_key is None:
				self._client = AsyncOpenAI(base_url=self.base_url, timeout=self.timeout)
			else:
				self._client = AsyncOpenAI(
					api_key=self.api_key,
					base_url=self.base_url,
					timeout=self.timeout,
				)
		return self._client

	@property
	def client(self) -> AsyncOpenAI:
		"""get the AsyncOpenAI client."""
		return self._get_client()
