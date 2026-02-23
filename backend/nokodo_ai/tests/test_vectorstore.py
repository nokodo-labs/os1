import pytest

from nokodo_ai import JSONObject, Vectorstore
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter


@pytest.mark.asyncio
async def test_vectorstore_forwards_adapter_calls() -> None:
	store = Vectorstore(
		collection="test-collection",
		adapter=QdrantVectorstoreAdapter(location=":memory:"),
	)

	ids = ["a1", "a2"]
	metadata: list[JSONObject] = [{"lang": "en"}, {"lang": "fr"}]
	chunks = [
		Chunk(id=ids[0], content="hello", embedding=[0.1, 0.2], metadata=metadata[0]),
		Chunk(id=ids[1], content="world", embedding=[0.3, 0.4], metadata=metadata[1]),
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
async def test_vectorstore_collection_field() -> None:
	store = Vectorstore(
		collection="my-namespace",
		adapter=QdrantVectorstoreAdapter(location=":memory:"),
	)

	assert store.collection == "my-namespace"
	await store.ensure_collection(vector_size=1)
	await store.add(
		[
			Chunk(
				id="id1",
				content="content",
				embedding=[0.1],
				metadata={"k": "v"},
			)
		]
	)


@pytest.mark.asyncio
async def test_vectorstore_create_supports_adapter_dict_shorthand() -> None:
	store = Vectorstore.create(
		"my-namespace",
		adapter={"type": "qdrant", "location": ":memory:"},
	)

	assert store.collection == "my-namespace"
	assert store.adapter.type == "qdrant.vectorstore"

	await store.ensure_collection(vector_size=1)
	await store.add(
		[
			Chunk(
				id="id1",
				content="content",
				embedding=[0.1],
				metadata={"k": "v"},
			)
		]
	)
