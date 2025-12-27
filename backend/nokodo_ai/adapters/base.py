"""base adapter infrastructure shared by all adapters."""

from __future__ import annotations

from abc import ABC

from pydantic import Field, PrivateAttr, model_validator

from nokodo_ai.base import Base


class BaseAdapter(Base, ABC):
	"""base infrastructure all adapters share.

	provides common functionality like configuration, logging, and lifecycle management.
	concrete provider bases (e.g., BaseOpenAIAdapter) inherit from this.
	"""

	pass


class BaseApiAdapter[ClientType](Base, ABC):
	"""
	base adapter for API-based adapters.
	"""

	api_key: str | None = Field(default=None, description="API key for the service")
	base_url: str | None = Field(
		default=None,
		description="Base URL for the service API (for proxies or custom endpoints)",
	)
	timeout: float = Field(default=60.0, description="Request timeout in seconds")
	_client: ClientType = PrivateAttr()

	@model_validator(mode="after")
	def _init_client(self) -> BaseApiAdapter[ClientType]:
		"""initialize the API client after model creation."""
		self._client = self._get_client()
		return self

	def _get_client(self) -> ClientType:
		"""get (or create) the API client.

		must be implemented by subclasses.
		"""
		raise NotImplementedError("subclasses must implement _get_client()")
