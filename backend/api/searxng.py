"""searxng API client.

pure HTTP client for searxng search instances.
does not depend on any application-level code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)

_USER_AGENT = "NokodoAI/1.0 (https://nokodo.ai)"


@dataclass(frozen=True, slots=True)
class SearxngSearchHit:
	"""a single search result from a searxng instance."""

	url: str
	title: str
	content: str
	score: float


class SearxngClient:
	"""async client for a SearXNG instance."""

	def __init__(
		self,
		*,
		instance_url: str,
		timeout: float = 10,
	) -> None:
		self._base_url = instance_url.rstrip("/")
		self._timeout = timeout

	async def search(
		self,
		query: str,
		*,
		max_results: int = 20,
		categories: list[str] | None = None,
		language: str = "all",
		safesearch: int = 1,
		time_range: str = "",
	) -> list[SearxngSearchHit]:
		"""search using the SearXNG instance.

		args:
			query: search query.
			max_results: maximum number of results to return.
			categories: optional category filters (e.g. ["general"]).
			language: language filter (default "all").
			safesearch: 0=off, 1=moderate, 2=strict.
			time_range: time range filter (e.g. "day", "week", "month").

		returns:
			list of search hits sorted by relevance score (descending).

		raises:
			httpx.HTTPStatusError: on non-2xx response.
			httpx.RequestError: on connection / timeout errors.
		"""
		params: dict[str, str | int] = {
			"q": query,
			"format": "json",
			"pageno": 1,
			"safesearch": safesearch,
			"language": language,
		}
		if time_range:
			params["time_range"] = time_range
		if categories:
			params["categories"] = ",".join(categories)

		headers = {
			"User-Agent": _USER_AGENT,
			"Accept": "application/json",
		}
		url = f"{self._base_url}/search"

		async with httpx.AsyncClient(timeout=self._timeout) as http:
			resp = await http.get(url, params=params, headers=headers)
			resp.raise_for_status()
			data = resp.json()

		raw: list[dict[str, float | str]] = data.get("results") or []
		ranked = sorted(raw, key=lambda x: float(x.get("score", 0)), reverse=True)
		return [
			SearxngSearchHit(
				url=str(h["url"]),
				title=str(h.get("title", "")),
				content=str(h.get("content", "")),
				score=float(h.get("score", 0.0)),
			)
			for h in ranked[:max_results]
		]
