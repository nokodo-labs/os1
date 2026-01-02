"""base ollama adapter - shared client infrastructure for ollama APIs."""

from __future__ import annotations

from pydantic import Field, PrivateAttr

from ..base import BaseAdapter


class BaseOllamaAdapter(BaseAdapter):
	"""shared infrastructure for all ollama adapters.

	provides:
	- ollama client initialization
	- base_url configuration
	- timeout settings
	"""

	base_url: str = Field(default="http://localhost:11434")
	timeout: float = Field(default=120.0)
	_client: object | None = PrivateAttr(default=None)
