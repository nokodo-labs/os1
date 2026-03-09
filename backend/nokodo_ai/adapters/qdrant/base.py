"""base qdrant adapter - shared client infrastructure for qdrant APIs."""

from __future__ import annotations

from pydantic import Field
from qdrant_client import AsyncQdrantClient

from ..base import BaseClientAdapter


class BaseQdrantAdapter(BaseClientAdapter[AsyncQdrantClient]):
	"""shared infrastructure for all qdrant adapters."""

	host: str | None = Field(default=None, description="qdrant host for remote mode")
	port: int | None = Field(default=None, description="qdrant REST port")
	grpc_port: int | None = Field(default=None, description="qdrant gRPC port")
	https: bool | None = Field(default=None, description="use HTTPS for remote mode")
	use_grpc: bool = Field(default=True, description="prefer qdrant gRPC transport")
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

		# structured remote mode
		if self.host is not None:
			return AsyncQdrantClient(
				host=self.host,
				port=self.port or 6333,
				grpc_port=self.grpc_port or 6334,
				prefer_grpc=self.use_grpc,
				https=self.https or False,
				api_key=self.api_key,
				timeout=timeout,
			)

		# URL-based remote mode
		if self.base_url is None:
			raise ValueError(
				"must provide either 'location' for local mode, "
				"'host' for structured remote mode, or 'base_url' for remote mode"
			)

		return AsyncQdrantClient(
			url=self.base_url,
			api_key=self.api_key,
			timeout=timeout,
			prefer_grpc=self.use_grpc,
			grpc_port=self.grpc_port or 6334,
		)

	async def close(self) -> None:
		await self._client.close()
