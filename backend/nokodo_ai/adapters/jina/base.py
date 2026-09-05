"""base jina adapter - shared client infrastructure for jina APIs."""

import httpx

from ..base import BaseClientAdapter


JINA_DEFAULT_BASE_URL = "https://api.jina.ai/v1"


class BaseJinaAdapter(BaseClientAdapter[httpx.AsyncClient]):
	"""shared infrastructure for all jina adapters.

	base_url also targets self-hosted jina-compatible servers
	(vllm, llama.cpp, text-embeddings-inference, ...).
	"""

	def _get_client(self) -> httpx.AsyncClient:
		headers: dict[str, str] = {}
		if self.api_key is not None:
			headers["Authorization"] = f"Bearer {self.api_key}"

		return httpx.AsyncClient(
			base_url=self.base_url or JINA_DEFAULT_BASE_URL,
			headers=headers,
			timeout=self.timeout,
		)

	async def close(self) -> None:
		await self._client.aclose()
