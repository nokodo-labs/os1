"""base anthropic adapter - shared client infrastructure for anthropic APIs."""

from __future__ import annotations

from typing import Any, Literal

from anthropic import AsyncAnthropic
from pydantic import Field

from ...base import Base
from ..base import BaseClientAdapter


class CacheControlConfig(Base):
	"""cache control configuration for Anthropic prompt caching."""

	type: Literal["ephemeral"] = "ephemeral"
	ttl: Literal["5m", "1h"] = "5m"


def _normalize_anthropic_base_url(base_url: str) -> str:
	url = base_url.strip().rstrip("/")
	if url.endswith("/v1"):
		return url[:-3]
	return url


class BaseAnthropicAdapter(BaseClientAdapter[AsyncAnthropic]):
	"""shared infrastructure for all anthropic adapters.

	provides:
	- anthropic client initialization
	- api_key management
	- timeout and retry settings
	"""

	cache_control: CacheControlConfig = Field(
		default_factory=CacheControlConfig,
		description="Cache control for Anthropic prompt caching.",
	)

	def _get_client(self) -> AsyncAnthropic:
		"""get (or create) an AsyncAnthropic client."""
		args: dict[str, Any] = {}
		args["timeout"] = self.timeout
		if self.api_key is not None:
			args["api_key"] = self.api_key
		if self.base_url is not None:
			args["base_url"] = _normalize_anthropic_base_url(self.base_url)

		return AsyncAnthropic(**args)

	async def close(self) -> None:
		await self._client.close()
