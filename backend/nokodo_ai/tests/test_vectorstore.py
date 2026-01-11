import pytest

from nokodo_ai import JSONObject, Vectorstore
from nokodo_ai.adapters.base.vectorstores import BaseVectorstoreAdapter, SearchResult


AddCall = tuple[list[str], list[list[float]], list[str], list[JSONObject] | None]


class _StubVectorstoreAdapter(BaseVectorstoreAdapter):
	def __init__(self) -> None:
		self.add_calls: list[AddCall] = []
		self.search_calls: list[tuple[list[float], int]] = []
		self.delete_calls: list[list[str]] = []

	async def add(
		self,
		ids: list[str],
		embeddings: list[list[float]],
		contents: list[str],
		metadata: list[JSONObject] | None = None,
	) -> None:
		self.add_calls.append((ids, embeddings, contents, metadata))

	async def search(
		self,
		embedding: list[float],
		*,
		limit: int = 10,
	) -> list[SearchResult]:
		self.search_calls.append((embedding, limit))
		return [
			SearchResult(
				id="doc1",
				content="hello",
				score=0.9,
				metadata={"rank": 1},
			)
		]

	async def delete(self, ids: list[str]) -> None:
		self.delete_calls.append(ids)


@pytest.mark.asyncio
async def test_vectorstore_forwards_adapter_calls() -> None:
	adapter = _StubVectorstoreAdapter()
	store = Vectorstore(adapter=adapter)

	ids = ["a1", "a2"]
	embeddings = [[0.1, 0.2], [0.3, 0.4]]
	contents = ["hello", "world"]
	metadata: list[JSONObject] = [{"lang": "en"}, {"lang": "fr"}]

	await store.add(ids, embeddings, contents, metadata)
	results = await store.search([0.5, 0.6], limit=5)
	await store.delete(ids)

	assert adapter.add_calls == [(ids, embeddings, contents, metadata)]
	assert adapter.search_calls == [([0.5, 0.6], 5)]
	assert adapter.delete_calls == [ids]

	assert results[0].id == "doc1"
	assert results[0].metadata == {"rank": 1}
