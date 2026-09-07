"""base google adapter - shared client infrastructure for google genai APIs."""

import google.genai as genai
from google.genai.client import AsyncClient
from pydantic import Field

from ..base import BaseClientAdapter


class BaseGoogleAdapter(BaseClientAdapter[AsyncClient]):
	"""shared infrastructure for all google genai adapters."""

	use_vertex_ai: bool = Field(
		default=False,
		description=("use vertex ai credentials instead of the developer api key"),
	)
	project: str | None = Field(
		default=None,
		description="vertex ai project id (required when use_vertex_ai=true)",
	)
	location: str | None = Field(
		default=None,
		description="vertex ai region (required when use_vertex_ai=true)",
	)

	def _get_client(self) -> AsyncClient:
		# google-genai takes no generic request timeout, so BaseApiAdapter.timeout
		# is kept for consistency but never passed to the client.

		if self.use_vertex_ai:
			if self.project is None or self.project.strip() == "":
				raise ValueError("project is required when use_vertex_ai=true")
			if self.location is None or self.location.strip() == "":
				raise ValueError("location is required when use_vertex_ai=true")
			return genai.Client(
				vertexai=True,
				project=self.project,
				location=self.location,
			).aio

		if self.api_key is None or self.api_key.strip() == "":
			raise ValueError("api_key is required when use_vertex_ai=false")
		return genai.Client(api_key=self.api_key).aio

	async def close(self) -> None:
		await self._client.aclose()
