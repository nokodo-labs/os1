"""perplexity API client.

thin wrapper around the official perplexityai SDK.
supports both agentic chat-completion search and web search.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from perplexity import AsyncPerplexity, omit
from perplexity.types import SearchCreateResponse, StreamChunk


if TYPE_CHECKING:
	from api.settings import (
		PerplexityModel,
		SearchContextUsage,
		SearchRecencyFilter,
	)


logger = logging.getLogger(__name__)

type PerplexitySearchMode = Literal["agentic", "web"]

_DEFAULT_SYSTEM_PROMPT = (
	"you are a web search assistant. provide accurate, up-to-date answers "
	"based on the search results. be concise and factual."
)


@dataclass(frozen=True, slots=True)
class PerplexitySearchResult:
	"""a single search result from perplexity's web search API."""

	title: str
	url: str
	snippet: str
	date: str | None = None
	last_updated: str | None = None


@dataclass(frozen=True, slots=True)
class PerplexityImageResult:
	"""a single image result returned by perplexity chat completions."""

	url: str
	title: str | None = None
	source_url: str | None = None


@dataclass(frozen=True, slots=True)
class PerplexitySearchResponse:
	"""response from a perplexity search operation.

	contains ALL results returned by the search, not just cited ones.
	"""

	content: str
	results: list[PerplexitySearchResult]
	images: list[PerplexityImageResult]
	mode: PerplexitySearchMode


class PerplexityClient:
	"""async client for the perplexity web search API."""

	def __init__(self, api_key: str) -> None:
		self._api_key = api_key

	async def search(
		self,
		query: str,
		max_results: int | None = None,
		search_recency_filter: SearchRecencyFilter | None = None,
		search_domain_filter: list[str] | None = None,
	) -> PerplexitySearchResponse:
		"""run a web search using perplexity's native search endpoint.

		returns search results (snippets, titles, URLs) - no AI summary.
		all results are returned, giving full visibility into what was searched.

		args:
			query: natural-language search query.
			max_results: max number of results to return.
			search_recency_filter: restrict to time window.
			search_domain_filter: restrict to specific domains (allowlist).

		returns:
			PerplexitySearchResponse with all search results.

		raises:
			perplexity.APIStatusError: on non-2xx response.
			perplexity.APIConnectionError: on connection/timeout errors.
		"""
		async with AsyncPerplexity(api_key=self._api_key) as client:
			response: SearchCreateResponse = await client.search.create(
				query=query,
				max_results=max_results if max_results is not None else omit,
				search_recency_filter=search_recency_filter,
				search_domain_filter=search_domain_filter,
			)

		results = [
			PerplexitySearchResult(
				title=r.title,
				url=r.url,
				snippet=r.snippet,
				date=r.date,
				last_updated=r.last_updated,
			)
			for r in response.results
		]
		return PerplexitySearchResponse(
			content=_format_search_results(results),
			results=results,
			images=[],
			mode="web",
		)

	async def agentic_search(
		self,
		query: str,
		model: PerplexityModel,
		system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
		temperature: float = 0.2,
		search_context_usage: SearchContextUsage = "medium",
		search_recency_filter: SearchRecencyFilter | None = None,
		return_images: bool = False,
		max_results: int | None = None,
		search_domain_filter: list[str] | None = None,
	) -> PerplexitySearchResponse:
		"""run agentic search through perplexity chat completions.

		returns perplexity's synthesized answer plus the full ``search_results``
		field, which is broader than the active citation URLs.
		"""
		async with AsyncPerplexity(api_key=self._api_key) as client:
			response: StreamChunk = await client.chat.completions.create(
				messages=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": query},
				],
				model=model,
				temperature=temperature,
				stream=False,
				web_search_options={"search_context_size": search_context_usage},
				search_recency_filter=search_recency_filter,
				search_domain_filter=search_domain_filter,
				num_search_results=max_results if max_results is not None else omit,
				return_images=return_images,
			)

		results = [
			PerplexitySearchResult(
				title=r.title,
				url=r.url,
				snippet=r.snippet or "",
				date=r.date,
				last_updated=r.last_updated,
			)
			for r in response.search_results or []
		]
		return PerplexitySearchResponse(
			content=_completion_content(response),
			results=results,
			images=_extract_images(response),
			mode="agentic",
		)


def _completion_content(response: StreamChunk) -> str:
	if not response.choices:
		logger.warning("perplexity response has no choices")
		return ""
	content = response.choices[0].message.content
	if isinstance(content, str):
		return content
	if content is None:
		return ""
	return str(content)


def _format_search_results(results: list[PerplexitySearchResult]) -> str:
	parts: list[str] = []
	for i, result in enumerate(results, 1):
		parts.append(f"[{i}] {result.title}\n{result.snippet}")
	return "\n\n".join(parts)


def _extract_images(response: StreamChunk) -> list[PerplexityImageResult]:
	extra = response.model_extra or {}
	for key in ("images", "image_results"):
		images = _parse_images(extra.get(key))
		if images:
			return images
	return []


def _parse_images(value: object) -> list[PerplexityImageResult]:
	if not isinstance(value, list):
		return []
	parsed: list[PerplexityImageResult] = []
	for item in value:
		if isinstance(item, str) and item:
			parsed.append(PerplexityImageResult(url=item))
		elif isinstance(item, Mapping):
			item_mapping = dict(item)
			url = _first_str(item_mapping, "url", "image_url")
			if url is None:
				continue
			parsed.append(
				PerplexityImageResult(
					url=url,
					title=_first_str(item_mapping, "title", "alt"),
					source_url=_first_str(item_mapping, "source_url", "source"),
				)
			)
	return parsed


def _first_str(source: Mapping[object, object], *keys: str) -> str | None:
	for key in keys:
		value = source.get(key)
		if isinstance(value, str) and value:
			return value
	return None
