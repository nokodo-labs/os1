"""web search dispatcher - routes to the configured search agent."""

from __future__ import annotations

import logging

from api.settings import SearchAgent, settings
from nokodo_ai.utils.typeid import TypeID

from .agent import search_agentic
from .models import WebSearchError, WebSearchResult
from .perplexity import search_perplexity


logger = logging.getLogger(__name__)


async def search_web(
	query: str,
	*,
	limit: int | None = None,
	search_agent: SearchAgent | None = None,
	agent_id_override: TypeID | None = None,
) -> WebSearchResult:
	"""perform an agentic web search using the configured provider.

	dispatches to the active search agent from settings.web_search.

	args:
		query: natural-language search query.
		limit: maximum number of sources to include.
		search_agent: override the default search agent (None = use settings).
		agent_id_override: override the default agent ID (None = use settings).

	returns:
		WebSearchResult with summary and citations.

	raises:
		WebSearchError: if the search fails or the provider is misconfigured.
	"""
	ws = settings.web_search
	agent = search_agent or ws.search_agent
	if agent == "perplexity":
		return await search_perplexity(query)
	elif agent == "native":
		return await search_agentic(
			query, limit=limit, agent_id_override=agent_id_override
		)
	else:
		raise WebSearchError(f"unsupported search agent: {agent}")
