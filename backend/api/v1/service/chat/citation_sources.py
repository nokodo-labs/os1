"""citation sources exposed to chat models and clients."""

from typing import TypedDict

from api.schemas.message import CitationSource
from nokodo_ai.types.json import JSONArray, JSONObject


CITABLE_SOURCES_KEY = "_citable_sources"
"""SDK metadata key; persisted as ``citable_sources`` in the private namespace."""


class CitableSource(TypedDict):
	"""resource the assistant may cite."""

	source_type: str
	source_id: str
	title: str | None


def citation_source(
	source_type: CitationSource,
	source_id: object,
	title: str | None,
) -> CitableSource:
	"""build one citation source."""
	return CitableSource(
		source_type=source_type.value,
		source_id=str(source_id),
		title=title,
	)


def with_citable_sources(
	metadata: JSONObject | None,
	sources: list[CitableSource],
) -> JSONObject:
	"""merge citation sources into message metadata."""
	serialized_sources: JSONArray = [
		{
			"source_type": source["source_type"],
			"source_id": source["source_id"],
			"title": source["title"],
		}
		for source in sources
	]
	return {
		**(metadata or {}),
		CITABLE_SOURCES_KEY: serialized_sources,
	}
