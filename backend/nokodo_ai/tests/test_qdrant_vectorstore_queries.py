"""qdrant adapter request-construction tests against a mocked client.

bm25/sparse vectors are computed server-side by qdrant, so these tests assert
the requests this platform builds (collection config, prefetch/fusion shapes,
vector naming) and result plumbing - not the BM25 algorithm itself.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client.models import (
	Document,
	FilterSelector,
	Fusion,
	FusionQuery,
	Modifier,
	PointIdsList,
	VectorParams,
)

from nokodo_ai.adapters.base.vectorstores import Chunk, ChunkFilter, FieldMatch
from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter


class _Recorder:
	"""async callable capturing keyword arguments and returning a canned result."""

	def __init__(self, result: Any = None) -> None:
		self.calls: list[dict[str, Any]] = []
		self._result = result

	async def __call__(self, *args: Any, **kwargs: Any) -> Any:
		self.calls.append(dict(kwargs))
		return self._result


def _adapter() -> QdrantVectorstoreAdapter:
	return QdrantVectorstoreAdapter(location=":memory:")


def _empty_points() -> SimpleNamespace:
	return SimpleNamespace(points=[])


async def test_hybrid_builds_dense_and_bm25_prefetch_with_rrf(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _adapter()
	recorder = _Recorder(_empty_points())
	monkeypatch.setattr(adapter._client, "query_points", recorder)

	await adapter.search("coll", query=[0.1, 0.2], text_query="solar panels", limit=7)

	call = recorder.calls[0]
	prefetch = call["prefetch"]
	assert [stage.using for stage in prefetch] == ["dense", "bm25"]
	assert prefetch[0].query == [0.1, 0.2]
	bm25_query = prefetch[1].query
	assert isinstance(bm25_query, Document)
	assert bm25_query.model == "Qdrant/bm25"
	assert bm25_query.text == "solar panels"
	# each prefetch stage overfetches for the fusion stage.
	assert all(stage.limit == max(7 * 3, 30) for stage in prefetch)
	fusion_query = call["query"]
	assert isinstance(fusion_query, FusionQuery)
	assert fusion_query.fusion == Fusion.RRF
	assert call["limit"] == 7


async def test_hybrid_dbsf_fusion_flag(monkeypatch: pytest.MonkeyPatch) -> None:
	adapter = _adapter()
	recorder = _Recorder(_empty_points())
	monkeypatch.setattr(adapter._client, "query_points", recorder)

	await adapter.search(
		"coll", query=[0.1, 0.2], text_query="q", limit=3, fusion="dbsf"
	)

	assert recorder.calls[0]["query"].fusion == Fusion.DBSF


async def test_sparse_queries_bm25_document(monkeypatch: pytest.MonkeyPatch) -> None:
	adapter = _adapter()
	recorder = _Recorder(_empty_points())
	monkeypatch.setattr(adapter._client, "query_points", recorder)

	await adapter.search("coll", text_query="hello world", limit=3)

	call = recorder.calls[0]
	query = call["query"]
	assert isinstance(query, Document)
	assert query.model == "Qdrant/bm25"
	assert query.text == "hello world"
	assert call["using"] == "bm25"


async def test_dense_search_addresses_named_dense_vector(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _adapter()
	recorder = _Recorder(_empty_points())
	monkeypatch.setattr(adapter._client, "query_points", recorder)

	await adapter.search("coll", query=[0.1, 0.2], limit=3)

	assert recorder.calls[0]["using"] == "dense"


async def test_dense_grouped_search_addresses_named_dense_vector(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _adapter()
	recorder = _Recorder(SimpleNamespace(groups=[]))
	monkeypatch.setattr(adapter._client, "query_points_groups", recorder)

	await adapter.search(
		"coll", query=[0.1, 0.2], limit=3, group_by="resource_id", group_size=2
	)

	call = recorder.calls[0]
	assert call["using"] == "dense"
	assert call["group_by"] == "resource_id"
	assert call["group_size"] == 2


@pytest.mark.parametrize("sparse", [True, False])
async def test_ensure_collection_always_names_dense_vector(
	monkeypatch: pytest.MonkeyPatch, sparse: bool
) -> None:
	adapter = _adapter()
	created = _Recorder()
	monkeypatch.setattr(adapter._client, "create_collection", created)
	monkeypatch.setattr(adapter._client, "collection_exists", _Recorder(False))
	indexed = _Recorder()
	monkeypatch.setattr(adapter._client, "create_payload_index", indexed)

	await adapter.ensure_collection(
		"coll", vector_size=4, sparse=sparse, indexes={"owner_id": "keyword"}
	)

	kwargs = created.calls[0]
	dense_config = kwargs["vectors_config"]["dense"]
	assert isinstance(dense_config, VectorParams)
	assert dense_config.size == 4
	if sparse:
		assert kwargs["sparse_vectors_config"]["bm25"].modifier == Modifier.IDF
	else:
		assert kwargs["sparse_vectors_config"] is None
	assert indexed.calls[0]["field_name"] == "owner_id"


async def test_add_sparse_attaches_bm25_document(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _adapter()
	recorder = _Recorder()
	monkeypatch.setattr(adapter._client, "upsert", recorder)
	chunk = Chunk(
		id="c1",
		content="hello world",
		metadata={"resource_type": "file_content"},
		embedding=[0.1, 0.2],
	)

	await adapter.add("coll", [chunk], sparse=True)

	point = recorder.calls[0]["points"][0]
	assert point.vector["dense"] == [0.1, 0.2]
	bm25_vector = point.vector["bm25"]
	assert isinstance(bm25_vector, Document)
	assert bm25_vector.model == "Qdrant/bm25"
	assert bm25_vector.text == "hello world"


async def test_add_plain_writes_named_dense_only(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _adapter()
	recorder = _Recorder()
	monkeypatch.setattr(adapter._client, "upsert", recorder)
	chunk = Chunk(id="c1", content="hello", metadata={}, embedding=[0.1, 0.2])

	await adapter.add("coll", [chunk], sparse=False)

	point = recorder.calls[0]["points"][0]
	assert point.vector == {"dense": [0.1, 0.2]}


@pytest.mark.parametrize(
	("target", "selector_type"),
	[
		(["chunk-1"], PointIdsList),
		(
			ChunkFilter(all_of=[FieldMatch(key="resource_id", value="file-1")]),
			FilterSelector,
		),
	],
)
async def test_update_delete_fields_builds_qdrant_selector(
	monkeypatch: pytest.MonkeyPatch,
	target: list[str] | ChunkFilter,
	selector_type: type[PointIdsList] | type[FilterSelector],
) -> None:
	adapter = _adapter()
	adapter._known_collections.add("coll")
	deleted = _Recorder()
	monkeypatch.setattr(adapter._client, "delete_payload", deleted)
	if isinstance(target, list):
		monkeypatch.setattr(
			adapter._client,
			"retrieve",
			_Recorder(
				[
					SimpleNamespace(id=adapter._to_point_id(chunk_id))
					for chunk_id in target
				]
			),
		)

	await adapter.update("coll", target, delete_fields=["obsolete"])

	assert deleted.calls[0]["keys"] == ["obsolete"]
	assert isinstance(deleted.calls[0]["points"], selector_type)


async def test_update_can_set_and_remove_payload_fields(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	adapter = _adapter()
	adapter._known_collections.add("coll")
	updated = _Recorder()
	deleted = _Recorder()
	monkeypatch.setattr(adapter._client, "set_payload", updated)
	monkeypatch.setattr(adapter._client, "delete_payload", deleted)
	target = ChunkFilter(all_of=[FieldMatch(key="resource_id", value="file-1")])

	await adapter.update(
		"coll",
		target,
		payload={"nullable": None},
		delete_fields=["obsolete"],
	)

	assert updated.calls[0]["payload"] == {"nullable": None}
	assert deleted.calls[0]["keys"] == ["obsolete"]
	assert updated.calls[0]["points"] == deleted.calls[0]["points"]


async def test_update_rejects_payload_delete_field_intersection() -> None:
	adapter = _adapter()
	target = ChunkFilter(all_of=[FieldMatch(key="resource_id", value="file-1")])

	with pytest.raises(ValueError, match="cannot contain the same key"):
		await adapter.update(
			"coll",
			target,
			payload={"shared": None},
			delete_fields=["shared"],
		)
