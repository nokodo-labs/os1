import pytest

from nokodo_ai import JSONObject, Vectorstore
from nokodo_ai.adapters.base.vectorstores import (
	Chunk,
	ChunkFilter,
	FieldMatch,
	FieldMatchAny,
)
from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter


# -- helpers -----------------------------------------------------------------


def make_store(collection: str) -> Vectorstore:
	return Vectorstore(
		collection=collection,
		adapter=QdrantVectorstoreAdapter(location=":memory:"),
	)


def make_chunk(
	chunk_id: str,
	embedding: list[float],
	content: str = "",
	metadata: dict | None = None,
) -> Chunk:
	return Chunk(
		id=chunk_id, content=content, embedding=embedding, metadata=metadata or {}
	)


@pytest.mark.asyncio
async def test_vectorstore_forwards_adapter_calls() -> None:
	store = make_store("test-collection")

	ids = ["a1", "a2"]
	metadata: list[JSONObject] = [{"lang": "en"}, {"lang": "fr"}]
	chunks = [
		make_chunk(ids[0], [0.1, 0.2], content="hello", metadata=metadata[0]),
		make_chunk(ids[1], [0.3, 0.4], content="world", metadata=metadata[1]),
	]

	await store.ensure_collection(vector_size=2)
	await store.add(chunks)
	results = await store.search(query=[0.5, 0.6], limit=5)
	await store.delete([c.id for c in chunks])
	assert results
	assert all(r.id in {"a1", "a2"} for r in results)
	assert any(r.metadata in metadata for r in results)
	assert all(0.0 <= r.score <= 1.0 for r in results)
	assert all(isinstance(r.embedding, list) for r in results)


@pytest.mark.asyncio
async def test_group_by_returns_best_hit_per_resource() -> None:
	store = make_store("group-by-test")
	await store.ensure_collection(vector_size=2)
	# resource A has two chunks: a1 close to the query, a2 far from it.
	# resource B has a single chunk.
	await store.add(
		[
			make_chunk(
				"a1", [1.0, 0.0], content="alpha near", metadata={"resource_id": "A"}
			),
			make_chunk(
				"a2", [0.0, 1.0], content="alpha far", metadata={"resource_id": "A"}
			),
			make_chunk(
				"b1", [0.9, 0.1], content="bravo", metadata={"resource_id": "B"}
			),
		]
	)

	results = await store.search(query=[1.0, 0.0], limit=10, group_by="resource_id")

	# exactly one hit per distinct resource_id, deduped by the backend.
	resource_ids = [r.metadata.get("resource_id") for r in results]
	assert sorted(resource_ids) == ["A", "B"]
	# for resource A, the better-scoring chunk a1 must be the one returned.
	by_resource = {r.metadata.get("resource_id"): r.id for r in results}
	assert by_resource["A"] == "a1"


@pytest.mark.asyncio
async def test_group_by_limit_bounds_distinct_resources() -> None:
	store = make_store("group-by-limit")
	await store.ensure_collection(vector_size=2)
	# three resources, two chunks each.
	chunks = []
	for rid in ("A", "B", "C"):
		chunks.append(make_chunk(f"{rid}1", [1.0, 0.0], metadata={"resource_id": rid}))
		chunks.append(make_chunk(f"{rid}2", [0.0, 1.0], metadata={"resource_id": rid}))
	await store.add(chunks)

	results = await store.search(query=[1.0, 0.0], limit=2, group_by="resource_id")

	# limit bounds distinct resources, not raw chunks.
	assert len(results) == 2
	assert len({r.metadata.get("resource_id") for r in results}) == 2


@pytest.mark.asyncio
async def test_group_size_returns_multiple_chunks_per_group() -> None:
	store = make_store("group-size-test")
	await store.ensure_collection(vector_size=2)
	# resource A has two chunks; resource B has one.
	await store.add(
		[
			make_chunk("a1", [1.0, 0.0], metadata={"resource_id": "A"}),
			make_chunk("a2", [0.9, 0.1], metadata={"resource_id": "A"}),
			make_chunk("b1", [0.8, 0.2], metadata={"resource_id": "B"}),
		]
	)

	results = await store.search(
		query=[1.0, 0.0], limit=10, group_by="resource_id", group_size=2
	)

	# both of A's chunks come back plus B's single chunk.
	ids = {r.id for r in results}
	assert ids == {"a1", "a2", "b1"}


@pytest.mark.asyncio
async def test_vectorstore_collection_field() -> None:
	store = make_store("my-namespace")

	assert store.collection == "my-namespace"
	await store.ensure_collection(vector_size=1)
	await store.add([make_chunk("id1", [0.1], content="content", metadata={"k": "v"})])


@pytest.mark.asyncio
async def test_vectorstore_create_supports_adapter_dict_shorthand() -> None:
	store = Vectorstore.create(
		"my-namespace",
		adapter={"type": "qdrant", "location": ":memory:"},
	)

	assert store.collection == "my-namespace"
	assert store.adapter.type == "qdrant.vectorstore"

	await store.ensure_collection(vector_size=1)
	await store.add([make_chunk("id1", [0.1], content="content", metadata={"k": "v"})])


# -- ChunkFilter construction ------------------------------------------------


def test_chunk_filter_all_of_accepts_field_match_and_match_any() -> None:
	f = ChunkFilter(
		all_of=[
			FieldMatch(key="resource_type", value="note"),
			FieldMatchAny(key="allowed_user_ids", values=["u1", "u2"]),
		]
	)
	assert len(f.all_of) == 2
	assert isinstance(f.all_of[0], FieldMatch)
	assert isinstance(f.all_of[1], FieldMatchAny)
	assert f.any_of == []


def test_chunk_filter_any_of_accepts_field_match_and_match_any() -> None:
	f = ChunkFilter(
		all_of=[FieldMatch(key="resource_type", value="thread")],
		any_of=[
			FieldMatch(key="owner_id", value="u1"),
			FieldMatchAny(key="allowed_group_ids", values=["g1", "g2"]),
		],
	)
	assert len(f.all_of) == 1
	assert len(f.any_of) == 2
	assert isinstance(f.any_of[1], FieldMatchAny)
	assert f.any_of[1].values == ["g1", "g2"]


def test_chunk_filter_empty_defaults() -> None:
	f = ChunkFilter()
	assert f.all_of == []
	assert f.any_of == []


# -- Vectorstore.update - list[str] path -------------------------------------


@pytest.mark.asyncio
async def test_update_by_id_list_patches_payload() -> None:
	store = make_store("update-test")
	await store.ensure_collection(vector_size=2)
	await store.add(
		[make_chunk("c1", [0.1, 0.2], content="hello", metadata={"tag": "old"})]
	)

	await store.update(["c1"], payload={"tag": "new"})

	results = await store.search(query=[0.1, 0.2], limit=1)
	assert results
	assert results[0].metadata.get("tag") == "new"


@pytest.mark.asyncio
async def test_update_by_id_list_raises_on_missing_chunk() -> None:
	store = make_store("update-missing")
	await store.ensure_collection(vector_size=2)
	await store.add([make_chunk("present", [0.1, 0.2])])

	with pytest.raises(ValueError, match="chunks not found"):
		await store.update(["present", "ghost"], payload={"k": "v"})


@pytest.mark.asyncio
async def test_update_by_id_list_noop_on_empty_list() -> None:
	store = make_store("update-empty")
	# should not raise even though collection does not exist yet
	await store.update([], payload={"k": "v"})


@pytest.mark.asyncio
async def test_update_noop_when_payload_is_none() -> None:
	store = make_store("update-none")
	# must not raise regardless of whether collection exists
	await store.update(["any-id"], payload=None)


# -- Vectorstore.update - ChunkFilter path -----------------------------------


@pytest.mark.asyncio
async def test_update_by_filter_patches_matching_chunks() -> None:
	store = make_store("update-filter")
	await store.ensure_collection(vector_size=2)
	await store.add(
		[
			make_chunk("n1", [0.1, 0.2], content="a", metadata={"rt": "note"}),
			make_chunk("t1", [0.3, 0.4], content="b", metadata={"rt": "thread"}),
		]
	)

	target = ChunkFilter(all_of=[FieldMatch(key="rt", value="note")])
	await store.update(target, payload={"acl": "updated"})

	results = await store.search(query=[0.1, 0.2], limit=2)
	by_id = {r.id: r for r in results}
	assert by_id["n1"].metadata.get("acl") == "updated"
	# thread chunk must be untouched
	assert "acl" not in by_id.get("t1", make_chunk("t1", [])).metadata


@pytest.mark.asyncio
async def test_update_by_filter_silent_when_no_match() -> None:
	store = make_store("update-filter-nomatch")
	# no collection created - should not raise
	target = ChunkFilter(all_of=[FieldMatch(key="rt", value="note")])
	await store.update(target, payload={"acl": "x"})


# -- FieldMatchAny via update filter -----------------------------------------


@pytest.mark.asyncio
async def test_update_with_field_match_any_in_all_of() -> None:
	"""all_of accepts FieldMatchAny - patches all chunks whose field is in the list."""
	store = make_store("update-matchany")
	await store.ensure_collection(vector_size=2)
	await store.add(
		[
			make_chunk("x1", [0.1, 0.2], metadata={"color": "red"}),
			make_chunk("x2", [0.3, 0.4], metadata={"color": "blue"}),
			make_chunk("x3", [0.5, 0.6], metadata={"color": "green"}),
		]
	)

	target = ChunkFilter(all_of=[FieldMatchAny(key="color", values=["red", "blue"])])
	await store.update(target, payload={"flagged": True})

	results = await store.search(query=[0.1, 0.2], limit=3)
	by_id = {r.id: r for r in results}
	assert by_id["x1"].metadata.get("flagged") is True
	assert by_id["x2"].metadata.get("flagged") is True
	assert "flagged" not in by_id.get("x3", make_chunk("x3", [])).metadata


# -- Qdrant _build_field_condition float handling -----------------------------


def test_qdrant_build_field_condition_string_uses_match_value() -> None:
	from qdrant_client.models import MatchValue

	cond = QdrantVectorstoreAdapter._build_field_condition(
		FieldMatch(key="status", value="active")
	)
	assert cond.key == "status"
	assert isinstance(cond.match, MatchValue)
	assert cond.match.value == "active"


def test_qdrant_build_field_condition_int_uses_match_value() -> None:
	from qdrant_client.models import MatchValue

	cond = QdrantVectorstoreAdapter._build_field_condition(
		FieldMatch(key="count", value=42)
	)
	assert isinstance(cond.match, MatchValue)
	assert cond.match.value == 42


def test_qdrant_build_field_condition_bool_uses_match_value() -> None:
	from qdrant_client.models import MatchValue

	cond = QdrantVectorstoreAdapter._build_field_condition(
		FieldMatch(key="active", value=True)
	)
	assert isinstance(cond.match, MatchValue)
	assert cond.match.value is True


def test_qdrant_build_field_condition_integral_float_coerces_to_int() -> None:
	"""integral floats (e.g. 5.0) should be sent as int via MatchValue."""
	from qdrant_client.models import MatchValue

	cond = QdrantVectorstoreAdapter._build_field_condition(
		FieldMatch(key="score", value=5.0)
	)
	assert isinstance(cond.match, MatchValue)
	assert cond.match.value == 5
	assert isinstance(cond.match.value, int)


def test_qdrant_build_field_condition_non_integral_float_uses_range() -> None:
	"""non-integral floats must use Range(gte=lte=value) for numeric matching."""
	from qdrant_client.models import Range

	cond = QdrantVectorstoreAdapter._build_field_condition(
		FieldMatch(key="threshold", value=0.75)
	)
	assert cond.match is None
	assert isinstance(cond.range, Range)
	assert cond.range.gte == 0.75
	assert cond.range.lte == 0.75


def test_qdrant_build_field_condition_match_any() -> None:
	from qdrant_client.models import MatchAny

	cond = QdrantVectorstoreAdapter._build_field_condition(
		FieldMatchAny(key="tags", values=["a", "b"])
	)
	assert isinstance(cond.match, MatchAny)
	assert cond.match.any == ["a", "b"]
