"""base voyageai adapter - shared client infrastructure for voyageai APIs."""

from __future__ import annotations

from typing import Any

from voyageai import AsyncClient

from ..base import BaseClientAdapter


class BaseVoyageAIAdapter(BaseClientAdapter[AsyncClient]):
	"""shared infrastructure for all voyageai adapters."""

	def _get_client(self) -> AsyncClient:
		args: dict[str, Any] = {}
		if self.api_key is not None:
			args["api_key"] = self.api_key
		if self.base_url is not None:
			args["base_url"] = self.base_url
		if self.timeout != 60.0:
			args["timeout"] = self.timeout

		return AsyncClient(**args)

	async def close(self) -> None:
		pass
