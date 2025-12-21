"""base ollama adapter - shared client infrastructure for ollama APIs."""

from __future__ import annotations

from nokodo_ai.adapters.base import BaseAdapter


class BaseOllamaAdapter(BaseAdapter):
	"""shared infrastructure for all ollama adapters.

	provides:
	- ollama client initialization
	- base_url configuration
	- timeout settings
	"""

	def __init__(
		self,
		*,
		base_url: str = "http://localhost:11434",
		timeout: float = 120.0,
	) -> None:
		"""initialize ollama adapter.

		args:
			base_url: ollama server URL
			timeout: request timeout in seconds
		"""
		self.base_url = base_url
		self.timeout = timeout
		# client will be lazily initialized when needed
		self._client = None
