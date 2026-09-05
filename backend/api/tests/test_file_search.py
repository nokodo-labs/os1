"""file search service behavior with precomputed vector results.

the vector store is faked at the service seam (per the global test stub);
these tests assert OUR behavior: mode-to-query construction, content-hit to
parent-file mapping, ACL re-checks, gates, and autocomplete matching.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File, FileSource, FileStatus
from api.models.user import User
from api.schemas.file import FileSearchFilters
from api.schemas.search import SearchMode, SearchParams
from api.tests.factories import create_user, principal_for
from api.v1.service.files import search as file_search_service
from api.v1.service.files.search import _file_id_for_hit, search_files
from nokodo_ai.adapters.base.vectorstores import ChunkSearchResult
from nokodo_ai.utils.typeid import new_typeid


async def _file(
	db_session: AsyncSession,
	owner: User,
	filename: str,
	description: str | None = None,
) -> File:
	file = File(
		id=new_typeid("file"),
		owner_id=owner.id,
		source=FileSource.USER_UPLOADED,
		storage_backend="local",
		storage_key=f"tests/search/{new_typeid('file')}",
		filename=filename,
		mime_type="text/plain",
		size_bytes=1,
		description=description,
		status=FileStatus.AVAILABLE,
	)
	db_session.add(file)
	await db_session.flush()
	return file


def _content_hit(parent_id: str, score: float, text: str) -> ChunkSearchResult:
	return ChunkSearchResult(
		id=f"chunk-{parent_id}-{score}",
		content=text,
		score=score,
		metadata={
			"resource_type": "file_content",
			"parent_resource_id": parent_id,
			"char_start": 0,
			"char_end": len(text),
			"chunk_index": 0,
			"chunk_count": 1,
		},
	)


def _file_hit(file_id: str, score: float, text: str) -> ChunkSearchResult:
	return ChunkSearchResult(
		id=f"card-{file_id}",
		content=text,
		score=score,
		metadata={"resource_type": "file", "resource_id": file_id},
	)


# gates


async def test_include_deleted_forbidden_for_non_admin(
	db_session: AsyncSession,
) -> None:
	user = await create_user(db_session, "fs_gate_user")
	with pytest.raises(HTTPException) as exc:
		await search_files(
			"anything",
			db_session,
			principal_for(user),
			filters=FileSearchFilters(include_deleted=True),
		)
	assert exc.value.status_code == 403


async def test_include_deleted_requires_autocomplete_mode(
	db_session: AsyncSession,
) -> None:
	admin = await create_user(db_session, "fs_gate_admin", is_superuser=True)
	with pytest.raises(HTTPException) as exc:
		await search_files(
			"anything",
			db_session,
			principal_for(admin),
			search_params=SearchParams(mode=SearchMode.HYBRID),
			filters=FileSearchFilters(include_deleted=True),
		)
	assert exc.value.status_code == 422


# mode -> vector query construction


@pytest.mark.parametrize(
	("mode", "expect_dense", "expect_sparse"),
	[
		(SearchMode.DENSE, True, False),
		(SearchMode.SPARSE, False, True),
		(SearchMode.HYBRID, True, True),
	],
)
async def test_mode_builds_expected_vector_query(
	monkeypatch: pytest.MonkeyPatch,
	db_session: AsyncSession,
	mode: SearchMode,
	expect_dense: bool,
	expect_sparse: bool,
) -> None:
	user = await create_user(db_session, f"fs_mode_{mode.value}")
	await db_session.commit()
	captured: dict[str, object] = {}

	async def _fake_search(**kwargs: object) -> list[ChunkSearchResult]:
		captured.update(kwargs)
		return []

	monkeypatch.setattr(file_search_service, "search", _fake_search)

	await search_files(
		"solar panels",
		db_session,
		principal_for(user),
		search_params=SearchParams(mode=mode),
	)

	if expect_dense:
		assert captured["query"] is not None
	else:
		assert captured["query"] is None
	assert captured["text_query"] == ("solar panels" if expect_sparse else None)


# content-hit mapping and acl re-check


async def test_hybrid_maps_hits_and_recheks_acl(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	owner = await create_user(db_session, "fs_map_owner")
	other_owner = await create_user(db_session, "fs_map_other")
	origin = await _file(db_session, owner, "notes.txt")
	card_file = await _file(db_session, owner, "cards.txt", description="cards")
	foreign = await _file(db_session, other_owner, "secret.txt")
	await db_session.commit()

	hits = [
		# highest score but inaccessible: must be dropped by the SQL re-check.
		_content_hit(str(foreign.id), 0.95, "classified body"),
		_content_hit(str(origin.id), 0.90, "solar body text"),
		_file_hit(str(card_file.id), 0.50, "cards.txt card"),
	]

	async def _fake_search(**kwargs: object) -> list[ChunkSearchResult]:
		_ = kwargs
		return hits

	monkeypatch.setattr(file_search_service, "search", _fake_search)

	scored = await search_files(
		"solar",
		db_session,
		principal_for(owner),
		search_params=SearchParams(mode=SearchMode.HYBRID),
	)

	ids = [str(s.item.id) for s in scored]
	assert str(foreign.id) not in ids
	assert ids.index(str(origin.id)) < ids.index(str(card_file.id))
	origin_scored = next(s for s in scored if str(s.item.id) == str(origin.id))
	assert origin_scored.score == 0.90
	matched = origin_scored.hit.matched_chunks
	assert matched and "solar body text" in str(matched)


async def test_duplicate_hits_dedupe_to_best_score(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	owner = await create_user(db_session, "fs_dedupe_owner")
	origin = await _file(db_session, owner, "dedupe.txt")
	await db_session.commit()

	async def _fake_search(**kwargs: object) -> list[ChunkSearchResult]:
		_ = kwargs
		return [
			_content_hit(str(origin.id), 0.80, "first chunk"),
			_content_hit(str(origin.id), 0.60, "second chunk"),
			_file_hit(str(origin.id), 0.40, "card"),
		]

	monkeypatch.setattr(file_search_service, "search", _fake_search)

	scored = await search_files(
		"q",
		db_session,
		principal_for(owner),
		search_params=SearchParams(mode=SearchMode.HYBRID),
	)

	assert len([s for s in scored if str(s.item.id) == str(origin.id)]) == 1
	assert scored[0].score == 0.80


# autocomplete tier


async def test_autocomplete_matches_filename_and_respects_acl(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, "fs_auto_owner")
	other = await create_user(db_session, "fs_auto_other")
	mine = await _file(db_session, owner, "solar-report.txt")
	theirs = await _file(db_session, other, "solar-secret.txt")
	await db_session.commit()

	scored = await search_files(
		"solar",
		db_session,
		principal_for(owner),
		search_params=SearchParams(mode=SearchMode.AUTOCOMPLETE),
	)

	ids = {str(s.item.id) for s in scored}
	assert str(mine.id) in ids
	assert str(theirs.id) not in ids


# hit -> file id resolution


def test_file_id_for_hit_resolves_content_and_card_hits() -> None:
	assert _file_id_for_hit(_content_hit("parent-1", 0.5, "x")) == "parent-1"
	assert _file_id_for_hit(_file_hit("file-1", 0.5, "x")) == "file-1"
	orphan = ChunkSearchResult(
		id="c",
		content="x",
		score=0.5,
		metadata={"resource_type": "file_content"},
	)
	assert _file_id_for_hit(orphan) is None
