"""base qdrant adapter - shared client infrastructure for qdrant APIs."""

from __future__ import annotations

from pydantic import Field
from qdrant_client import AsyncQdrantClient

from ..base import BaseClientAdapter


class BaseQdrantAdapter(BaseClientAdapter[AsyncQdrantClient]):
	"""shared infrastructure for all qdrant adapters."""

	location: str | None = Field(
		default=None,
		description="path or :memory: for local/in-memory mode",
	)

	def _get_client(self) -> AsyncQdrantClient:
		"""get (or create) an AsyncQdrantClient."""
		timeout = int(self.timeout) if self.timeout is not None else None

		# local/in-memory mode
		if self.location is not None:
			return AsyncQdrantClient(
				location=self.location,
				timeout=timeout,
			)

		# remote mode - base_url required, api_key optional (self-hosted)
		if self.base_url is None:
			raise ValueError(
				"must provide either 'location' for local mode, "
				"or 'base_url' for remote mode"
			)

		return AsyncQdrantClient(
			url=self.base_url,
			api_key=self.api_key,
			timeout=timeout,
		)

	async def close(self) -> None:
		await self._client.close()
