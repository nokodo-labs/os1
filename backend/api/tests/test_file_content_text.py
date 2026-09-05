"""tests for extracted file body text storage and content access."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.file import File, FileSource, FileStatus
from api.models.user import User
from api.permissions import DefaultResourceAccess
from api.schemas.user import UserCreate
from api.settings import settings
from api.storage.base import FileInfo, MimeType, StorageBackend
from api.tests.factories import make_principal
from api.v1.service import users as user_service
from api.v1.service.authentication import Principal
from api.v1.service.files import core as file_service
from api.v1.service.files import derived_files as derived_files_service
from api.v1.service.files.derived_files import find_derived_file
from api.v1.service.files.text_contents import extraction as extraction_service
from api.v1.service.files.text_contents import store as store_service
from api.v1.service.files.text_contents import vectors as vectors_service
from api.v1.service.files.text_contents.extraction import chunk_loaded_text
from api.v1.service.files.text_contents.store import (
	_slice_lines,
	delete_extracted_text,
	has_extracted_text_child,
	read_extracted_text,
	read_file_content_lines,
	store_extracted_text,
)
from api.v1.service.files.text_contents.vectors import _chunk_hit, query_file_content
from nokodo_ai.adapters.base.vectorstores import ChunkSearchResult
from nokodo_ai.loaders import Text
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.fixture(autouse=True)
def _stub_embedding_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
	"""pin chunk-size clamping to a fixed capacity; no embedding model here."""

	async def _capacity(session: object = None) -> int:
		return 8192

	monkeypatch.setattr(extraction_service, "embedding_token_capacity", _capacity)


class _DictStorageBackend(StorageBackend):
	"""in-memory storage backend tracking objects and deletions for assertions."""

	def __init__(self) -> None:
		super().__init__("memory")
		self.objects: dict[str, bytes] = {}
		self.deleted: list[str] = []

	async def put(
		self,
		key: str,
		data: bytes | AsyncIterator[bytes],
		content_type: MimeType,
	) -> None:
		if isinstance(data, bytes):
			self.objects[key] = data
			return
		parts: list[bytes] = []
		async for chunk in data:
			parts.append(chunk)
		self.objects[key] = b"".join(parts)

	async def get(self, key: str) -> AsyncIterator[bytes]:
		return _single_chunk(self.objects[key])

	async def delete(self, key: str) -> None:
		self.deleted.append(key)
		self.objects.pop(key, None)

	async def exists(self, key: str) -> bool:
		return key in self.objects

	async def stat(self, key: str) -> FileInfo | None:
		return None

	async def copy(self, src_key: str, dst_key: str) -> None:
		return None

	async def get_url(self, key: str, expires_in: int | None = None) -> str | None:
		return None


async def _single_chunk(data: bytes) -> AsyncIterator[bytes]:
	yield data


def _file_record() -> File:
	return File(
		id=new_typeid("file"),
		owner_id=new_typeid("user"),
		source=FileSource.USER_UPLOADED,
		storage_backend="memory",
		storage_key="tests/file",
		filename="report.txt",
		mime_type="text/plain",
		size_bytes=10,
		checksum_sha256=None,
		description="stored file",
		status=FileStatus.AVAILABLE,
		projects=[],
	)


def _principal() -> Principal:
	return make_principal(slug="content_text_user", is_superuser=True)


async def _create_user(
	db_session: AsyncSession, slug: str, is_superuser: bool = True
) -> User:
	return await user_service.create_user(
		UserCreate(
			email=f"{slug}@example.com",
			username=slug,
			password="password123",
			is_superuser=is_superuser,
		),
		db_session,
	)


async def _find_extracted_text_child(
	parent_id: TypeID, session: AsyncSession
) -> File | None:
	return await find_derived_file(parent_id, FileSource.TEXT_EXTRACTION, session)


async def _origin_file(db_session: AsyncSession, owner_id: object) -> File:
	"""persist an ordinary origin file owned by the given user."""
	file = File(
		id=TypeID(new_typeid("file")),
		owner_id=owner_id,
		source=FileSource.USER_UPLOADED,
		storage_backend="memory",
		storage_key=f"tests/{new_typeid('file')}",
		filename="report.txt",
		mime_type="text/plain",
		size_bytes=10,
		status=FileStatus.AVAILABLE,
	)
	db_session.add(file)
	await db_session.flush()
	return file


# store / read / delete


async def test_store_and_read_round_trip(monkeypatch, db_session: AsyncSession) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_round")
	origin = await _origin_file(db_session, user.id)

	await store_extracted_text(origin, "line one\r\nline two\r\n", db_session)

	child = await _find_extracted_text_child(origin.id, db_session)
	assert child is not None
	# the extracted text is a distinct file row pointing back at the origin,
	# discriminated by its source and owned by no user.
	assert child.parent_file_id == str(origin.id)
	assert child.source == FileSource.TEXT_EXTRACTION
	assert child.owner_id is None
	assert child.id != origin.id
	# normalized: CRLF -> LF and surrounding whitespace stripped.
	assert await read_extracted_text(origin, db_session) == "line one\nline two"


async def test_store_empty_text_creates_empty_child(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_empty")
	origin = await _origin_file(db_session, user.id)

	await store_extracted_text(origin, "   \n  \t ", db_session)

	# no text, but a derived file still exists holding empty content.
	child = await _find_extracted_text_child(origin.id, db_session)
	assert child is not None
	assert child.size_bytes == 0
	assert await has_extracted_text_child(origin.id, db_session) is True
	assert await read_extracted_text(origin, db_session) == ""


async def test_store_replaces_in_place(monkeypatch, db_session: AsyncSession) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_replace")
	origin = await _origin_file(db_session, user.id)

	await store_extracted_text(origin, "first body", db_session)
	first = await _find_extracted_text_child(origin.id, db_session)
	assert first is not None
	first_id, first_key = first.id, first.storage_key

	await store_extracted_text(origin, "second body", db_session)
	second = await _find_extracted_text_child(origin.id, db_session)

	assert second is not None
	# the derived file row is reused (unique per origin), repointed at new bytes.
	assert second.id == first_id
	assert second.storage_key != first_key
	assert first_key in backend.deleted
	assert await read_extracted_text(origin, db_session) == "second body"


async def test_store_empty_after_text_clears_child_in_place(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_clear")
	origin = await _origin_file(db_session, user.id)

	await store_extracted_text(origin, "had text once", db_session)
	child = await _find_extracted_text_child(origin.id, db_session)
	assert child is not None
	old_key = child.storage_key

	await store_extracted_text(origin, "", db_session)

	# the child row stays (the marker persists) but now holds empty content; the
	# previous blob is dropped.
	again = await _find_extracted_text_child(origin.id, db_session)
	assert again is not None
	assert again.id == child.id
	assert old_key in backend.deleted
	assert await read_extracted_text(origin, db_session) == ""


async def test_read_extracted_text_handles_missing_blob(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_missing")
	origin = await _origin_file(db_session, user.id)
	await store_extracted_text(origin, "body", db_session)
	# drop the underlying object, leaving a dangling derived file row.
	backend.objects.clear()

	assert await read_extracted_text(origin, db_session) is None


async def test_delete_extracted_text_removes_child_and_blob(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_delete")
	origin = await _origin_file(db_session, user.id)
	await store_extracted_text(origin, "body", db_session)
	child = await _find_extracted_text_child(origin.id, db_session)
	assert child is not None
	key = child.storage_key

	await delete_extracted_text(origin, db_session)

	assert key in backend.deleted
	assert await _find_extracted_text_child(origin.id, db_session) is None


async def test_delete_extracted_text_noop_without_child(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_delnoop")
	origin = await _origin_file(db_session, user.id)

	await delete_extracted_text(origin, db_session)

	assert backend.deleted == []


async def test_derived_file_excluded_from_listing(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	admin = await _create_user(db_session, "ct_listing_admin")
	owner = await _create_user(db_session, "ct_listing", is_superuser=False)
	origin = await _origin_file(db_session, owner.id)
	await store_extracted_text(origin, "body text", db_session)
	child = await _find_extracted_text_child(origin.id, db_session)
	assert child is not None

	# the owner sees their file but never its owner-less derived text file.
	owner_principal = Principal.for_user(
		user=owner, group_ids=(), permissions=frozenset()
	)
	owner_ids = {
		str(f.id)
		for f in await file_service.list_files(
			db_session, principal=owner_principal, limit=100
		)
	}
	assert str(origin.id) in owner_ids
	assert str(child.id) not in owner_ids

	# an admin can see derived files to manage them.
	admin_principal = Principal.for_user(
		user=admin, group_ids=(), permissions=frozenset()
	)
	admin_ids = {
		str(f.id)
		for f in await file_service.list_files(
			db_session, principal=admin_principal, limit=100
		)
	}
	assert str(child.id) in admin_ids


async def test_default_file_access_excludes_derived_files(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	await _create_user(db_session, "ct_default_admin")
	owner = await _create_user(db_session, "ct_default_owner", is_superuser=False)
	other = await _create_user(db_session, "ct_default_other", is_superuser=False)
	origin = await _origin_file(db_session, owner.id)
	await store_extracted_text(origin, "body text", db_session)
	child = await _find_extracted_text_child(origin.id, db_session)
	assert child is not None

	# a default file access level grants every user-owned file, but never an
	# owner-less internal derivative.
	principal = Principal.for_user(
		user=other,
		group_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(file=AccessLevel.READER),
	)
	ids = {
		str(f.id)
		for f in await file_service.list_files(
			db_session, principal=principal, limit=100
		)
	}
	assert str(origin.id) in ids
	assert str(child.id) not in ids


# stored text aligns with chunk offsets


async def test_stored_text_offsets_match_chunks(
	monkeypatch, db_session: AsyncSession
) -> None:
	monkeypatch.setattr(
		settings.assets.content_vectorization, "chunking_algorithm", "recursive"
	)
	monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 40)
	monkeypatch.setattr(settings.assets.content_vectorization, "overlap_tokens", 5)
	monkeypatch.setattr(settings.assets.content_vectorization, "max_chunks", 50)
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _create_user(db_session, "ct_offsets")
	origin = await _origin_file(db_session, user.id)
	# CRLF input proves the stored (normalized) text and chunk char offsets
	# share the same coordinate space.
	raw = "\r\n".join(f"paragraph {index} " + "word " * 30 for index in range(6))

	await store_extracted_text(origin, raw, db_session)
	stored = await read_extracted_text(origin, db_session)
	assert stored is not None

	chunks = await chunk_loaded_text(
		Text(content=stored, status="loaded", source="plain")
	)
	assert chunks
	for chunk in chunks:
		char_start = chunk.metadata["char_start"]
		char_end = chunk.metadata["char_end"]
		assert isinstance(char_start, int)
		assert isinstance(char_end, int)
		assert stored[char_start:char_end].strip() == chunk.text


# query_file_content


async def test_query_file_content_slices_clean_text(
	monkeypatch, db_session: AsyncSession
) -> None:
	full_text = "alpha line\nbeta line\ngamma line\ndelta line"
	file = _file_record()
	char_start = full_text.index("beta")
	char_end = full_text.index("delta")

	async def fake_accessible(*_a: object, **_k: object) -> File:
		return file

	async def fake_embed(*_a: object, **_k: object) -> list[float]:
		return [0.1, 0.2]

	async def fake_text(*_a: object, **_k: object) -> str:
		return full_text

	async def fake_search(**_k: object) -> list[ChunkSearchResult]:
		return [
			ChunkSearchResult(
				id="c1",
				# embedding-prefixed stored chunk content (filename/description)
				content="report.txt\nstored file\nbeta line\ngamma line",
				metadata={
					"char_start": char_start,
					"char_end": char_end,
					"line_start": 2,
					"line_end": 3,
					"chunk_index": 0,
					"chunk_count": 2,
				},
				score=0.88,
			)
		]

	monkeypatch.setattr(vectors_service, "load_accessible_file", fake_accessible)
	monkeypatch.setattr(vectors_service, "embed_text", fake_embed)
	monkeypatch.setattr(vectors_service, "read_extracted_text", fake_text)
	monkeypatch.setattr(vectors_service, "search", fake_search)

	hits = await query_file_content(
		new_typeid("file"), "beta", db_session, principal=_principal(), limit=5
	)

	assert len(hits) == 1
	# clean body text sliced from the blob, not the embedding-prefixed content.
	assert hits[0].text == full_text[char_start:char_end].strip()
	assert "report.txt" not in hits[0].text
	assert hits[0].line_start == 2
	assert hits[0].line_end == 3
	assert hits[0].score == 0.88


async def test_query_file_content_falls_back_when_text_missing(
	monkeypatch, db_session: AsyncSession
) -> None:
	file = _file_record()

	async def fake_accessible(*_a: object, **_k: object) -> File:
		return file

	async def fake_embed(*_a: object, **_k: object) -> list[float]:
		return [0.1]

	async def fake_text(*_a: object, **_k: object) -> str | None:
		return None

	async def fake_search(**_k: object) -> list[ChunkSearchResult]:
		return [
			ChunkSearchResult(
				id="c1",
				content="actual chunk body",
				metadata={"char_start": 0, "char_end": 5},
				score=0.5,
			)
		]

	monkeypatch.setattr(vectors_service, "load_accessible_file", fake_accessible)
	monkeypatch.setattr(vectors_service, "embed_text", fake_embed)
	monkeypatch.setattr(vectors_service, "read_extracted_text", fake_text)
	monkeypatch.setattr(vectors_service, "search", fake_search)

	hits = await query_file_content(
		new_typeid("file"), "anything", db_session, principal=_principal()
	)

	assert hits[0].text == "actual chunk body"


# access enforcement


async def test_content_access_is_enforced(
	monkeypatch, db_session: AsyncSession
) -> None:
	async def deny(*_a: object, **_k: object) -> None:
		raise HTTPException(status_code=403, detail="forbidden")

	monkeypatch.setattr(store_service, "require_resource_access", deny)

	with pytest.raises(HTTPException) as exc:
		await read_file_content_lines(
			new_typeid("file"), db_session, principal=_principal(), line_start=1
		)
	assert exc.value.status_code == 403


# _slice_lines pure logic


def test_slice_lines_range() -> None:
	result = _slice_lines("l1\nl2\nl3\nl4\nl5", 2, 4)
	assert result.text == "l2\nl3\nl4"
	assert (result.line_start, result.line_end, result.total_lines) == (2, 4, 5)


def test_slice_lines_to_end_when_end_omitted() -> None:
	result = _slice_lines("l1\nl2\nl3", 2, None)
	assert result.text == "l2\nl3"
	assert result.line_end == 3


def test_slice_lines_to_end_when_end_nonpositive() -> None:
	result = _slice_lines("l1\nl2\nl3", 1, 0)
	assert result.text == "l1\nl2\nl3"
	assert result.line_end == 3


def test_slice_lines_clamps_overflow() -> None:
	result = _slice_lines("l1\nl2", 1, 99)
	assert result.text == "l1\nl2"
	assert result.line_end == 2


def test_slice_lines_start_beyond_end_is_empty() -> None:
	result = _slice_lines("l1\nl2\nl3", 5, 6)
	assert result.text == ""
	assert result.total_lines == 3


def test_slice_lines_without_text() -> None:
	assert _slice_lines(None, 1, 5).total_lines == 0
	assert _slice_lines("", 1, 5).total_lines == 0


# _chunk_hit pure logic


def test_chunk_hit_falls_back_when_range_out_of_bounds() -> None:
	hit = ChunkSearchResult(
		id="c1",
		content="fallback body",
		metadata={"char_start": 100, "char_end": 200, "line_start": 1, "line_end": 2},
		score=0.7,
	)
	result = _chunk_hit(hit, "short text")
	assert result.text == "fallback body"
	assert result.line_start == 1
	assert result.line_end == 2
