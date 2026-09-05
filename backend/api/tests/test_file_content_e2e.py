"""end-to-end file content pipeline against a real in-memory vector store.

runs real bytes -> extraction -> chunking -> embedding -> qdrant storage ->
dense retrieval (query_file_content + search_files) -> ACL scoping, with only
two seams faked: embeddings (deterministic topic-count vectors) and bm25
(local qdrant cannot run server-side inference without fastembed, so upserts
write the named dense vector only and text queries are stripped).
"""

from typing import Any

import pytest
from fastapi import HTTPException
from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File, FileSource, FileStatus
from api.models.user import User
from api.schemas.search import SearchMode, SearchParams
from api.settings import settings
from api.storage import get_storage_backend
from api.tests.factories import create_user, principal_for
from api.v1.service import vectorstores as vectorstores_service
from api.v1.service.files import processing as processing_service
from api.v1.service.files.derived_files import find_derived_file
from api.v1.service.files.processing import process_file
from api.v1.service.files.search import search_files
from api.v1.service.files.text_contents import (
	CONTENT_VECTOR_FINGERPRINT_KEY,
	query_file_content,
	read_extracted_text,
	vectorize_file_content,
)
from nokodo_ai.adapters.qdrant.vectorstores import QdrantVectorstoreAdapter
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.typeid import new_typeid


_TOPICS = ("solar", "granite", "jazz")

_BODY = (
	"Solar panel arrays convert sunlight into usable power. "
	"Solar adoption keeps rising as solar cells get cheaper.\n\n"
	"Granite forms deep underground from slowly cooled magma. "
	"Granite counters and granite monuments survive for ages.\n\n"
	"Jazz musicians improvise over swinging rhythm sections. "
	"Jazz clubs host late night jazz jam sessions downtown.\n"
)


def _topic_embedding(text: str) -> list[float]:
	"""deterministic embedding: one dimension per topic word count."""
	lowered = text.lower()
	counts = [float(lowered.count(topic)) for topic in _TOPICS]
	return [*counts, 0.001]


@pytest.fixture(autouse=True)
def _api_test_stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
	"""shadow the global no-op vectorstore stub: real local qdrant instead."""
	# never touch a configured live server from tests.
	monkeypatch.setattr(settings.assets.vector_database.qdrant, "url", ":memory:")
	vectorstores_service._vectorstore_adapter.cache_clear()
	vectorstores_service._cached_collection_name = None
	vectorstores_service._ensured_collections.clear()

	async def _fake_embed(
		self: EmbeddingModel, texts: list[str], input_type: str | None = None
	) -> list[list[float]]:
		_ = self, input_type
		return [_topic_embedding(text) for text in texts]

	monkeypatch.setattr(EmbeddingModel, "embed", _fake_embed)

	async def _dense_only_add(
		self: QdrantVectorstoreAdapter,
		collection_name: str,
		chunks: list,
		sparse: bool = False,
	) -> None:
		_ = sparse
		points = [
			PointStruct(
				id=self._to_point_id(chunk.id),
				payload=self._build_payload(chunk),
				vector={"dense": chunk.embedding},
			)
			for chunk in chunks
		]
		await self._client.upsert(collection_name=collection_name, points=points)

	monkeypatch.setattr(QdrantVectorstoreAdapter, "add", _dense_only_add)

	original_search = QdrantVectorstoreAdapter.search

	async def _dense_only_search(
		self: QdrantVectorstoreAdapter,
		collection_name: str,
		query: list[float] | None = None,
		text_query: str | None = None,
		**kwargs: Any,
	) -> list:
		_ = text_query
		return await original_search(
			self, collection_name, query=query, text_query=None, **kwargs
		)

	monkeypatch.setattr(QdrantVectorstoreAdapter, "search", _dense_only_search)


@pytest.fixture(autouse=True)
def _small_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
	"""force multiple chunks out of the short fixture body."""
	monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 30)
	monkeypatch.setattr(settings.assets.content_vectorization, "overlap_tokens", 0)


@pytest.fixture(autouse=True)
def _stub_description(monkeypatch: pytest.MonkeyPatch) -> None:
	"""description generation needs a chat model; pin a static description."""

	async def _fake_update(file: File, *args: object, **kwargs: object) -> None:
		_ = args, kwargs
		file.description = "quarterly research notes"

	monkeypatch.setattr(processing_service, "update_file_description", _fake_update)


async def _stored_file(db_session: AsyncSession, owner: User) -> File:
	"""persist a real text file through the registered local storage backend."""
	key = f"tests/e2e/{new_typeid('file')}.txt"
	data = _BODY.encode("utf-8")
	await get_storage_backend("local").put(key, data, "text/plain")
	file = File(
		id=new_typeid("file"),
		owner_id=owner.id,
		source=FileSource.USER_UPLOADED,
		storage_backend="local",
		storage_key=key,
		filename="report.txt",
		mime_type="text/plain",
		size_bytes=len(data),
		checksum_sha256="e2e-checksum",
		status=FileStatus.AVAILABLE,
	)
	db_session.add(file)
	await db_session.flush()
	return file


async def _content_chunks(file_id: object, db_session: AsyncSession) -> list:
	query_filter = vectorstores_service.child_resource_filter(
		vectorstores_service.VectorChunkResourceType.FILE,
		[str(file_id)],
		vectorstores_service.VectorChunkResourceType.FILE_CONTENT,
	)
	return await vectorstores_service.scroll_chunks(query_filter, db_session)


async def test_content_pipeline_end_to_end(db_session: AsyncSession) -> None:
	admin = await create_user(db_session, "e2e_admin", is_superuser=True)
	owner = await create_user(db_session, "e2e_owner")
	stranger = await create_user(db_session, "e2e_stranger")
	file = await _stored_file(db_session, owner)

	await process_file(file.id, db_session)
	await db_session.commit()

	# extracted text persisted as an owner-less derived file row.
	child = await find_derived_file(file.id, FileSource.TEXT_EXTRACTION, db_session)
	assert child is not None
	assert child.owner_id is None
	stored_text = await read_extracted_text(file, db_session)
	assert stored_text is not None
	assert stored_text.startswith("Solar panel arrays")

	# chunks actually landed in the vector store with retrieval metadata.
	chunks = await _content_chunks(file.id, db_session)
	assert len(chunks) >= 3
	for chunk in chunks:
		assert chunk.metadata["owner_id"] == str(owner.id)
		assert isinstance(chunk.metadata["char_start"], int)
		assert isinstance(chunk.metadata["char_end"], int)
	assert file.private_metadata.get(CONTENT_VECTOR_FINGERPRINT_KEY)

	# top-k content query returns the semantically closest chunk with clean
	# text sliced from the stored body at the recorded char offsets.
	hits = await query_file_content(
		file.id, "solar power efficiency", db_session, principal_for(owner), limit=2
	)
	assert hits
	top = hits[0]
	assert "solar" in top.text.lower()
	assert "report.txt" not in top.text
	assert top.char_start is not None and top.char_end is not None
	assert top.text == stored_text[top.char_start : top.char_end].strip()
	assert top.line_start is not None and top.line_end is not None
	lines = stored_text.split("\n")
	window = "\n".join(lines[top.line_start - 1 : top.line_end]).lower()
	assert "solar" in window

	# ranking is semantic: a different topic query surfaces its own chunk.
	jazz_hits = await query_file_content(
		file.id, "jazz improvisation", db_session, principal_for(owner), limit=1
	)
	assert "jazz" in jazz_hits[0].text.lower()

	# unified file search resolves content hits to the parent file.
	scored = await search_files(
		"solar",
		db_session,
		principal_for(owner),
		limit=5,
		search_params=SearchParams(mode=SearchMode.DENSE),
	)
	assert scored
	assert str(scored[0].item.id) == str(file.id)
	matched = scored[0].hit.matched_chunks
	assert matched and "solar" in str(matched).lower()

	# acl: a stranger sees nothing; content queries 404; admins see everything.
	stranger_scored = await search_files(
		"solar",
		db_session,
		principal_for(stranger),
		limit=5,
		search_params=SearchParams(mode=SearchMode.DENSE),
	)
	assert all(str(s.item.id) != str(file.id) for s in stranger_scored)
	with pytest.raises(HTTPException) as exc:
		await query_file_content(file.id, "solar", db_session, principal_for(stranger))
	assert exc.value.status_code == 404
	admin_hits = await query_file_content(
		file.id, "solar", db_session, principal_for(admin), limit=1
	)
	assert admin_hits


async def test_reprocessing_is_a_noop_when_current(db_session: AsyncSession) -> None:
	owner = await create_user(db_session, "e2e_noop_owner")
	file = await _stored_file(db_session, owner)

	await process_file(file.id, db_session)
	first_chunks = await _content_chunks(file.id, db_session)
	assert first_chunks

	batch = await vectorize_file_content(file, db_session)
	assert batch.skipped_reason == "already_current"
	assert len(await _content_chunks(file.id, db_session)) == len(first_chunks)
