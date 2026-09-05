"""base cohere adapter - shared client infrastructure for cohere APIs."""

from typing import Any

from cohere import AsyncClientV2

from ..base import BaseClientAdapter


class BaseCohereAdapter(BaseClientAdapter[AsyncClientV2]):
	"""shared infrastructure for all cohere adapters."""

	def _get_client(self) -> AsyncClientV2:
		args: dict[str, Any] = {}
		if self.api_key is not None:
			args["api_key"] = self.api_key
		if self.base_url is not None:
			args["base_url"] = self.base_url
		if self.timeout != 60.0:
			args["timeout"] = self.timeout

		return AsyncClientV2(**args)

	async def close(self) -> None:
		pass
