import pytest

from nokodo_ai import JSONObject, Vectorstore
from nokodo_ai.adapters.base.vectorstores import Chunk


@pytest.mark.asyncio
async def test_vectorstore_forwards_adapter_calls() -> None:
	store = Vectorstore(
		"qdrant",
		collection="test-collection",
		adapter={"type": "qdrant.vectorstore", "location": ":memory:"},
	)

	ids = ["a1", "a2"]
	metadata: list[JSONObject] = [{"lang": "en"}, {"lang": "fr"}]
	chunks = [
		Chunk(id=ids[0], content="hello", embedding=[0.1, 0.2], metadata=metadata[0]),
		Chunk(id=ids[1], content="world", embedding=[0.3, 0.4], metadata=metadata[1]),
	]

	await store.add(chunks)
	results = await store.search([0.5, 0.6], limit=5)
	await store.delete(chunks)
	assert results
	assert all(r.id in {"a1", "a2"} for r in results)
	assert any(r.metadata in metadata for r in results)
	assert all(0.0 <= r.score <= 1.0 for r in results)
	assert all(isinstance(r.embedding, list) for r in results)


@pytest.mark.asyncio
async def test_vectorstore_collection_field() -> None:
	store = Vectorstore(
		"qdrant",
		collection="my-namespace",
		adapter={"type": "qdrant.vectorstore", "location": ":memory:"},
	)

	assert store.collection == "my-namespace"
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
