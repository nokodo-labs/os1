"""base adapter infrastructure shared by all api-client adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field, PrivateAttr, model_validator

from ...base import Base
from .adapter import BaseAdapter


class BaseClientAdapter[ClientType](BaseAdapter, Base, ABC):
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
	def _init_client(self) -> BaseClientAdapter[ClientType]:
		"""initialize the API client after model creation."""
		self._client = self._get_client()
		return self

	@abstractmethod
	def _get_client(self) -> ClientType:
		"""get (or create) the API client.

		must be implemented by subclasses.
		"""
		raise NotImplementedError("subclasses must implement _get_client()")

	@abstractmethod
	async def close(self) -> None:
		"""close resources held by the adapter."""
		raise NotImplementedError("subclasses must implement close()")
