"""base openai adapter - shared client infrastructure for openai APIs."""

from __future__ import annotations

from openai import AsyncOpenAI

from ..base import BaseApiAdapter


class BaseOpenAIAdapter(BaseApiAdapter[AsyncOpenAI]):
	"""shared infrastructure for all openai adapters.

	provides:
	- openai client initialization
	- api_key management
	- base_url configuration (for proxies/custom endpoints)
	- timeout and retry settings
	"""

	def _get_client(self) -> AsyncOpenAI:
		"""get (or create) an AsyncOpenAI client."""
		args = {}
		args["timeout"] = self.timeout
		if self.api_key is not None:
			args["api_key"] = self.api_key
		if self.base_url is not None:
			args["base_url"] = self.base_url

		return AsyncOpenAI(**args)
