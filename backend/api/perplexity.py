"""perplexity API client.

pure HTTP client for the perplexity chat completions API.
does not depend on any application-level code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)

_BASE_URL = "https://api.perplexity.ai/chat/completions"

_DEFAULT_SYSTEM_PROMPT = (
	"you are a web search assistant. "
	"provide accurate, up-to-date answers based on the search results. "
	"be concise and factual."
)


@dataclass(frozen=True, slots=True)
class PerplexitySearchResponse:
	"""raw response from a perplexity search completion."""

	content: str
	citations: list[str]
	images: list[str]


class PerplexityClient:
	"""async client for the perplexity chat completions API."""

	def __init__(self, *, api_key: str) -> None:
		self._api_key = api_key

	async def search(
		self,
		query: str,
		*,
		model: str = "sonar",
		system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
		temperature: float = 0.2,
		search_context_usage: str = "medium",
		search_recency_filter: str | None = None,
		return_images: bool = False,
	) -> PerplexitySearchResponse:
		"""run a search query through perplexity's chat endpoint.

		args:
			query: natural-language search query.
			model: perplexity model (sonar, sonar-pro, etc.).
			system_prompt: system-level instruction for the model.
			temperature: sampling temperature (lower = more factual).
			search_context_usage: how much search context to use.
			search_recency_filter: restrict results to time window.
			return_images: include image URLs in the response.

		returns:
			PerplexitySearchResponse with content, citations, and images.

		raises:
			httpx.HTTPStatusError: on non-2xx response.
			httpx.RequestError: on connection / timeout errors.
		"""
		web_search_options: dict[str, object] = {
			"search_context_usage": search_context_usage,
		}
		if search_recency_filter is not None:
			web_search_options["search_recency_filter"] = search_recency_filter

		payload: dict[str, object] = {
			"model": model,
			"messages": [
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": query},
			],
			"temperature": temperature,
			"stream": False,
			"web_search_options": web_search_options,
			"return_images": return_images,
		}
		headers = {
			"Authorization": f"Bearer {self._api_key}",
			"Content-Type": "application/json",
		}
		async with httpx.AsyncClient(timeout=30.0) as http:
			resp = await http.post(_BASE_URL, json=payload, headers=headers)
			resp.raise_for_status()
			data = resp.json()

		content = ""
		choices: list[dict[str, object]] = data.get("choices") or []
		if choices:
			msg = choices[0].get("message")
			if isinstance(msg, dict):
				content = str(msg.get("content", ""))
		else:
			logger.warning("perplexity response has no choices")

		citations: list[str] = data.get("citations") or []
		images: list[str] = data.get("images") or []
		return PerplexitySearchResponse(
			content=content, citations=citations, images=images
		)
