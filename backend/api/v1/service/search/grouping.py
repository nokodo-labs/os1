"""resource hit grouping for chunk-level vector search results.

used when a resource is vectorized into multiple chunks and Qdrant returns
raw chunk hits that must be collapsed back to one result per resource.

note: most resources use group_by="resource_id" in Qdrant which handles
this server-side (top-1 chunk per resource, best score kept). this module
is only needed for resources with a two-tier type architecture (e.g. files,
where FILE and FILE_CONTENT chunks share a logical resource but have distinct
resource_ids in the vector store).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from nokodo_ai.adapters.base.vectorstores import ChunkSearchResult
from nokodo_ai.types.json import JSONArray, JSONObject


@dataclass(slots=True)
class ResourceHitGroup:
	"""all chunk hits for a single logical resource."""

	resource_id: str
	hits: list[ChunkSearchResult] = field(default_factory=list)

	@property
	def best_score(self) -> float:
		return max((hit.score for hit in self.hits), default=0.0)

	def matched_chunks(self, max_chunks: int, preview_chars: int) -> JSONArray:
		"""top-scoring chunk payloads, ordered by descending score."""
		chunks: JSONArray = []
		for hit in sorted(self.hits, key=lambda h: h.score, reverse=True)[:max_chunks]:
			payload: JSONObject = {
				"score": hit.score,
				"preview": hit.content[:preview_chars],
			}
			for key in (
				"resource_type",
				"chunk_index",
				"chunk_count",
				"page_number",
				"slide_number",
				"section_label",
				"paragraph_index",
				"line_start",
				"line_end",
				"column_start",
				"column_end",
				"char_start",
				"char_end",
				"text_loader",
				"chunking_algorithm",
			):
				value = hit.metadata.get(key)
				if value is not None:
					payload[key] = value
			chunks.append(payload)
		return chunks


def group_resource_hits(
	results: list[ChunkSearchResult],
	id_for_hit: Callable[[ChunkSearchResult], str | None],
) -> dict[str, ResourceHitGroup]:
	"""group Qdrant chunk hits by logical resource id.

	id_for_hit extracts the resource id from a hit; return None to skip
	a hit (e.g. malformed metadata). insertion order is preserved so
	results remain sorted by first-seen best score.
	"""
	groups: dict[str, ResourceHitGroup] = {}
	for hit in results:
		resource_id = id_for_hit(hit)
		if not resource_id:
			continue
		group = groups.setdefault(
			resource_id,
			ResourceHitGroup(resource_id=resource_id),
		)
		group.hits.append(hit)
	return groups
