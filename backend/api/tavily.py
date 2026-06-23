"""tavily API client.

pure HTTP client for tavily search and extract APIs.
does not depend on any application-level code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.tavily.com/search"
_EXTRACT_URL = "https://api.tavily.com/extract"


@dataclass(frozen=True, slots=True)
class TavilySearchHit:
	"""a single search result from the tavily search API."""

	url: str
	title: str
	content: str
	score: float


@dataclass(frozen=True, slots=True)
class TavilyExtractedPage:
	"""successfully extracted page content from the tavily extract API."""

	url: str
	raw_content: str


@dataclass(frozen=True, slots=True)
class TavilyExtractFailure:
	"""a URL that failed extraction."""

	url: str
	error: str


class TavilyClient:
	"""async client for the tavily search and extract APIs."""

	def __init__(self, api_key: str) -> None:
		self._api_key = api_key

	async def search(
		self,
		query: str,
		max_results: int = 5,
	) -> list[TavilySearchHit]:
		"""search the web using tavily.

		args:
			query: natural-language search query.
			max_results: maximum number of results to return.

		returns:
			list of search hits with url, title, content, and score.

		raises:
			httpx.HTTPStatusError: on non-2xx response.
			httpx.RequestError: on connection / timeout errors.
		"""
		headers = {
			"Content-Type": "application/json",
			"Authorization": f"Bearer {self._api_key}",
		}
		payload = {"query": query, "max_results": max_results}

		async with httpx.AsyncClient(timeout=30.0) as http:
			resp = await http.post(_SEARCH_URL, json=payload, headers=headers)
			resp.raise_for_status()
			data = resp.json()

		return [
			TavilySearchHit(
				url=r["url"],
				title=r.get("title", ""),
				content=r.get("content", ""),
				score=float(r.get("score", 0.0)),
			)
			for r in data.get("results") or []
		]

	async def extract(
		self,
		urls: list[str],
		extract_depth: str = "basic",
	) -> tuple[list[TavilyExtractedPage], list[TavilyExtractFailure]]:
		"""extract content from URLs using tavily.

		args:
			urls: list of URLs to extract content from.
			extract_depth: "basic" or "advanced".

		returns:
			tuple of (successful extractions, failed extractions).

		raises:
			httpx.HTTPStatusError: on non-2xx response.
			httpx.RequestError: on connection / timeout errors.
		"""
		if not urls:
			return [], []

		headers = {
			"Content-Type": "application/json",
			"Authorization": f"Bearer {self._api_key}",
		}
		payload = {"urls": urls, "extract_depth": extract_depth}

		async with httpx.AsyncClient(timeout=60.0) as http:
			resp = await http.post(_EXTRACT_URL, json=payload, headers=headers)
			resp.raise_for_status()
			data = resp.json()

		pages = [
			TavilyExtractedPage(
				url=r.get("url", ""),
				raw_content=r.get("raw_content", ""),
			)
			for r in data.get("results") or []
			if r.get("raw_content")
		]
		failures = [
			TavilyExtractFailure(
				url=f.get("url", ""),
				error=f.get("error", "unknown error"),
			)
			for f in data.get("failed_results") or []
		]
		return pages, failures
