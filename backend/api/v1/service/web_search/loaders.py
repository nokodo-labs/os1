"""web content loaders - fetch and extract content from URLs.

provides a unified interface for loading web page content, with
multiple backend engines (native httpx, tavily extract, etc.).

usage:
    from api.v1.service.web_search.loaders import fetch_url
    content = await fetch_url("https://example.com/article")
"""

from __future__ import annotations

import logging

import httpx

from api.settings import settings
from api.tavily import TavilyClient
from api.v1.service.web_search import WebSearchError


logger = logging.getLogger(__name__)


async def fetch_url(url: str) -> str:
	"""fetch content from a URL using the configured web loader engine.

	dispatches to the active engine from settings.web_search.web_loaders.

	args:
		url: the URL to fetch content from.

	returns:
		extracted text content from the page.

	raises:
		WebSearchError: if the fetch fails or the loader is misconfigured.
		httpx.HTTPStatusError: on non-2xx response (native engine).
		httpx.RequestError: on connection / timeout errors (native engine).
	"""
	ws = settings.web_search
	engine = ws.web_loaders.engine

	if engine == "tavily":
		return await _fetch_tavily(url)
	# native and playwright both use direct fetch for now
	return await _fetch_native(
		url,
		timeout=ws.web_loaders.timeout_seconds,
		user_agent=ws.web_loaders.user_agent,
	)


async def _fetch_native(url: str, *, timeout: int, user_agent: str) -> str:
	"""fetch page content directly via httpx."""
	headers = {"User-Agent": user_agent, "Accept": "text/html,*/*"}
	async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=True) as http:
		resp = await http.get(url, headers=headers)
		resp.raise_for_status()
		return resp.text


async def _fetch_tavily(url: str) -> str:
	"""fetch page content via the tavily extract API."""
	ws = settings.web_search
	api_key = ws.web_loaders.tavily.api_key
	if not api_key:
		raise WebSearchError(
			"tavily web loader requires an API key "
			"(settings.web_search.web_loaders.tavily.api_key)"
		)
	client = TavilyClient(api_key=api_key)
	pages, failures = await client.extract(
		[url],
		extract_depth=ws.web_loaders.tavily.extract_depth,
	)
	if failures:
		raise WebSearchError(f"tavily extraction failed for {url}: {failures[0].error}")
	if not pages:
		raise WebSearchError(f"tavily returned no content for {url}")
	return pages[0].raw_content


__all__ = [
	"fetch_url",
]
