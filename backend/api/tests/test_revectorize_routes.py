"""coverage for revectorize admin routes and the stale-targeting service."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_revision import AccessRevision
from api.models.file import File, FileSource, FileStatus
from api.models.memory import Memory
from api.models.note import Note
from api.models.thread import Thread
from api.models.user import User
from api.permissions import ResourceType
from api.v1.routers import calendar as calendar_router
from api.v1.routers import reminder_lists as reminder_lists_router
from api.v1.routers import search as search_router
from api.v1.service.authorization import ACL_REVISION_KEY
from api.v1.service.files.text_contents.vectors import (
	CONTENT_VECTOR_CONFIG_KEY,
	CONTENT_VECTOR_FINGERPRINT_KEY,
	CONTENT_VECTOR_PIPELINE_KEY,
	FILE_CONTENT_PIPELINE_VERSION,
)
from api.v1.service.search import aggregator
from api.v1.service.threads.content_vectors import (
	CONTENT_VECTORS_BUILT_AT_KEY,
	CONTENT_VECTORS_CONFIG_KEY,
	CONTENT_VECTORS_SCHEMA_KEY,
	THREAD_CONTENT_PIPELINE_VERSION,
	thread_passages_config_fp,
)
from api.v1.service.vectorize import StaleBy
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.utils.security import hash_password
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.mark.asyncio
async def test_reminders_and_calendar_events_revectorize_routes(
	client: AsyncClient,
	admin_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = cast("dict[str, str]", admin_auth["headers"])

	async def fake_vectorize_reminders(*args: object, **kwargs: object) -> int:
		_ = (args, kwargs)
		return 7

	async def fake_vectorize_calendar_events(*args: object, **kwargs: object) -> int:
		_ = (args, kwargs)
		return 11

	monkeypatch.setattr(
		reminder_lists_router,
		"vectorize_reminders",
		fake_vectorize_reminders,
	)
	monkeypatch.setattr(
		calendar_router,
		"vectorize_calendar_events",
		fake_vectorize_calendar_events,
	)

	reminders_response = await client.post(
		"/v1/reminders/revectorize",
		headers=headers,
	)
	calendar_response = await client.post(
		"/v1/calendars/events/revectorize",
		headers=headers,
	)

	assert reminders_response.status_code == 200
	assert reminders_response.json() == {"vectorized": 7}
	assert calendar_response.status_code == 200
	assert calendar_response.json() == {"vectorized": 11}


@pytest.mark.asyncio
async def test_search_revectorize_routes_dispatch(
	client: AsyncClient,
	admin_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""GET previews, POST rebuilds; `by` narrows both."""
	headers = cast("dict[str, str]", admin_auth["headers"])
	calls: list[object] = []

	async def fake_vectorize(
		db: object, by: object = None, **kwargs: object
	) -> dict[str, object]:
		_ = (db, kwargs)
		calls.append(("rebuild", by))
		return {"by": None}

	async def fake_count(by: Collection[StaleBy], db: object) -> dict[str, object]:
		_ = db
		calls.append(("count", set(by)))
		return {"by": []}

	monkeypatch.setattr(search_router, "vectorize", fake_vectorize)
	monkeypatch.setattr(search_router, "count_stale_vectors", fake_count)

	full = await client.post("/v1/search/revectorize", headers=headers)
	assert full.status_code == 200
	assert calls[-1] == ("rebuild", None)

	stale = await client.post(
		"/v1/search/revectorize?by=pipeline_version", headers=headers
	)
	assert stale.status_code == 200
	assert calls[-1] == ("rebuild", [StaleBy.PIPELINE_VERSION])

	preview_all = await client.get("/v1/search/revectorize", headers=headers)
	assert preview_all.status_code == 200
	assert calls[-1] == ("count", set(StaleBy))

	preview_one = await client.get("/v1/search/revectorize?by=config", headers=headers)
	assert preview_one.status_code == 200
	assert calls[-1] == ("count", {StaleBy.CONFIG})


@pytest.mark.asyncio
async def test_vectorize_by_targets_only_stale(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the stale path rebuilds/dispatches exactly the provenance-stale resources."""
	s = uuid4().hex[:8]
	user = User(
		email=f"vs_{s}@rvz.test",
		username=f"vs_{s}",
		hashed_password=hash_password("x"),
		is_active=True,
	)
	db_session.add(user)
	await db_session.flush()
	now = datetime.now(tz=UTC).isoformat()
	thread_stale = Thread(
		owner_id=user.id,
		title=f"stale_{s}",
		is_temporary=False,
	)
	thread_stale.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION - 1,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: thread_passages_config_fp(),
		}
	)
	thread_current = Thread(
		owner_id=user.id,
		title=f"current_{s}",
		is_temporary=False,
	)
	thread_current.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: thread_passages_config_fp(),
		}
	)

	def _file(metadata: dict[str, object]) -> File:
		file = File(
			id=TypeID(new_typeid("file")),
			owner_id=str(user.id),
			source=FileSource.USER_IMPORTED,
			storage_backend="local",
			storage_key=f"tests/{new_typeid('file')}",
			filename="imported.txt",
			mime_type="text/plain",
			size_bytes=10,
			status=FileStatus.AVAILABLE,
		)
		file.set_metadata(private=metadata)
		return file

	file_stale = _file(
		{
			CONTENT_VECTOR_FINGERPRINT_KEY: "fp",
			CONTENT_VECTOR_PIPELINE_KEY: FILE_CONTENT_PIPELINE_VERSION - 1,
			CONTENT_VECTOR_CONFIG_KEY: "cfg",
		}
	)
	file_current = _file(
		{
			CONTENT_VECTOR_FINGERPRINT_KEY: "fp",
			CONTENT_VECTOR_PIPELINE_KEY: FILE_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTOR_CONFIG_KEY: "cfg",
		}
	)
	db_session.add_all([thread_stale, thread_current, file_stale, file_current])
	await db_session.flush()

	stale_note_id = new_typeid("note")
	current_note_id = new_typeid("note")

	def _note_chunk(note_id: str, pipeline_v: int) -> Chunk:
		return Chunk(
			id=f"{note_id}-0",
			content="body",
			embedding=[0.0],
			metadata={
				"resource_type": VectorChunkResourceType.NOTE.value,
				"resource_id": str(note_id),
				"pipeline_v": pipeline_v,
				"config_fp": "cfg",
			},
		)

	async def _scroll(*args: object, **kwargs: object) -> list[Chunk]:
		_ = (args, kwargs)
		return [
			_note_chunk(str(stale_note_id), 0),
			_note_chunk(str(current_note_id), 1),
		]

	rebuilt: list[list[str]] = []

	async def _rebuild_notes(session: object, ids: list[TypeID]) -> int:
		_ = session
		rebuilt.append([str(i) for i in ids])
		return len(rebuilt[-1])

	dispatched_threads: list[str] = []

	async def _kiq(thread_id: str) -> None:
		dispatched_threads.append(thread_id)

	dispatched_files: list[str] = []
	forced_flags: list[bool] = []

	async def _start_task(
		session: object,
		principal: object,
		file_id: object,
		force: bool = False,
		**kwargs: object,
	) -> None:
		_ = (session, principal, kwargs)
		dispatched_files.append(str(file_id))
		forced_flags.append(force)

	async def _principal(user_id: object, session: object) -> object:
		_ = (user_id, session)
		return object()

	monkeypatch.setattr(aggregator, "scroll_chunks", _scroll)
	monkeypatch.setitem(
		aggregator._GENERIC_REBUILDERS, VectorChunkResourceType.NOTE, _rebuild_notes
	)
	monkeypatch.setattr(aggregator, "schedule_thread_content_vectorization", _kiq)
	monkeypatch.setattr(aggregator, "start_file_processing_task", _start_task)
	monkeypatch.setattr(aggregator, "load_principal_for_user", _principal)

	counts = await aggregator.count_stale_vectors(
		{StaleBy.PIPELINE_VERSION}, db_session
	)
	result = await aggregator.vectorize(db_session, by={StaleBy.PIPELINE_VERSION})

	assert result["by"] == [StaleBy.PIPELINE_VERSION.value]
	assert rebuilt == [[str(stale_note_id)]]
	assert str(thread_stale.id) in dispatched_threads
	assert str(thread_current.id) not in dispatched_threads
	assert str(file_stale.id) in dispatched_files
	assert str(file_current.id) not in dispatched_files
	# force=True is what makes dispatched file processing actually rebuild.
	assert forced_flags and all(forced_flags)
	# the GET preview and the POST rebuild derive from the same selectors:
	# counts must equal what the rebuild targeted (containment: parallel test
	# rows can add to the db-scanned sets).
	resources = counts["resources"]
	assert isinstance(resources, dict)
	assert resources[VectorChunkResourceType.NOTE.value] == 1
	thread_count = counts["thread_content"]
	file_count = counts["file_content"]
	assert isinstance(thread_count, int) and thread_count == len(dispatched_threads)
	assert isinstance(file_count, int) and file_count == len(dispatched_files)
	assert set(result.keys()) == {"by", "resources", "thread_content", "file_content"}
	assert set(counts.keys()) == {"by", "resources", "thread_content", "file_content"}


@pytest.mark.asyncio
async def test_vectorize_multi_cause_or_combines(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a thread stale by only ONE of two requested causes is still targeted."""
	s = uuid4().hex[:8]
	user = User(
		email=f"mc_{s}@rvz.test",
		username=f"mc_{s}",
		hashed_password=hash_password("x"),
		is_active=True,
	)
	db_session.add(user)
	await db_session.flush()
	now = datetime.now(tz=UTC).isoformat()
	version_stale = Thread(
		owner_id=user.id,
		title=f"vstale_{s}",
		is_temporary=False,
	)
	version_stale.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION - 1,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: thread_passages_config_fp(),
		}
	)
	config_stale = Thread(
		owner_id=user.id,
		title=f"cstale_{s}",
		is_temporary=False,
	)
	config_stale.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: "other-config",
		}
	)
	current = Thread(
		owner_id=user.id,
		title=f"cur_{s}",
		is_temporary=False,
	)
	current.set_metadata(
		private={
			CONTENT_VECTORS_SCHEMA_KEY: THREAD_CONTENT_PIPELINE_VERSION,
			CONTENT_VECTORS_BUILT_AT_KEY: now,
			CONTENT_VECTORS_CONFIG_KEY: thread_passages_config_fp(),
		}
	)
	db_session.add_all([version_stale, config_stale, current])
	await db_session.flush()

	async def _scroll(*args: object, **kwargs: object) -> list[Chunk]:
		_ = (args, kwargs)
		return []

	dispatched: list[str] = []

	async def _kiq(thread_id: str) -> None:
		dispatched.append(thread_id)

	monkeypatch.setattr(aggregator, "scroll_chunks", _scroll)
	monkeypatch.setattr(aggregator, "schedule_thread_content_vectorization", _kiq)

	await aggregator.vectorize(
		db_session, by={StaleBy.PIPELINE_VERSION, StaleBy.CONFIG}
	)

	assert str(version_stale.id) in dispatched
	assert str(config_stale.id) in dispatched
	assert str(current.id) not in dispatched


@pytest.mark.asyncio
async def test_acl_staleness_repairs_payload_without_reembedding(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	note_id = TypeID(new_typeid("note"))
	db_session.add(
		AccessRevision(
			resource_type=ResourceType.NOTE,
			resource_id=note_id,
			revision=3,
		)
	)
	await db_session.flush()

	async def _scroll(*args: object, **kwargs: object) -> list[Chunk]:
		_ = (args, kwargs)
		return [
			Chunk(
				id="acl-stale",
				content="",
				embedding=[],
				metadata={
					"resource_type": VectorChunkResourceType.NOTE.value,
					"resource_id": str(note_id),
					ACL_REVISION_KEY: 2,
				},
			)
		]

	synced: list[list[tuple[ResourceType, TypeID]]] = []

	async def _sync(
		resource_refs: list[tuple[ResourceType, TypeID]],
		db: AsyncSession,
	) -> None:
		assert db is db_session
		synced.append(resource_refs)

	monkeypatch.setattr(aggregator, "scroll_chunks", _scroll)
	monkeypatch.setattr(aggregator, "sync_resource_refs_vector_acl", _sync)

	counts = await aggregator.count_stale_vectors({StaleBy.ACL}, db_session)
	result = await aggregator.vectorize(db_session, by={StaleBy.ACL})
	expected_resources = {
		chunk_type.value: (1 if chunk_type is VectorChunkResourceType.NOTE else 0)
		for chunk_type in aggregator._GENERIC_CHUNK_TYPES
	}

	assert counts["resources"] == expected_resources
	assert result["resources"] == expected_resources
	assert synced == [[(ResourceType.NOTE, note_id)]]
	assert result["thread_content"] == 0
	assert result["file_content"] == 0


@pytest.mark.asyncio
async def test_vectorize_full_rebuild_covers_every_pipeline(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""by=None rebuilds all six resource types and dispatches every thread."""
	s = uuid4().hex[:8]
	user = User(
		email=f"fb_{s}@rvz.test",
		username=f"fb_{s}",
		hashed_password=hash_password("x"),
		is_active=True,
	)
	db_session.add(user)
	await db_session.flush()
	thread = Thread(owner_id=user.id, title=f"full_{s}", is_temporary=False)
	temp_thread = Thread(owner_id=user.id, title=f"temp_{s}", is_temporary=True)
	db_session.add_all([thread, temp_thread])
	await db_session.flush()

	called: dict[str, object] = {}

	def _fake(name: str, count: int):
		async def _impl(session: object, ids: object = None) -> int:
			called[name] = ids
			return count

		return _impl

	monkeypatch.setattr(aggregator, "vectorize_notes", _fake("notes", 1))
	monkeypatch.setattr(aggregator, "vectorize_threads", _fake("threads", 2))
	monkeypatch.setattr(aggregator, "vectorize_reminders", _fake("reminders", 3))
	monkeypatch.setattr(
		aggregator, "vectorize_calendar_events", _fake("calendar_events", 4)
	)
	monkeypatch.setattr(aggregator, "vectorize_files", _fake("files", 5))
	monkeypatch.setattr(aggregator, "vectorize_memories", _fake("memories", 6))

	dispatched: list[str] = []

	async def _kiq(thread_id: str) -> None:
		dispatched.append(thread_id)

	monkeypatch.setattr(aggregator, "schedule_thread_content_vectorization", _kiq)

	result = await aggregator.vectorize(db_session)

	assert set(called.keys()) == {
		"notes",
		"threads",
		"reminders",
		"calendar_events",
		"files",
		"memories",
	}
	assert all(ids is None for ids in called.values())
	resources = result["resources"]
	assert isinstance(resources, dict)
	assert resources[VectorChunkResourceType.NOTE.value] == 1
	assert resources[VectorChunkResourceType.FILE.value] == 5
	assert str(thread.id) in dispatched
	assert str(temp_thread.id) not in dispatched
	assert set(result.keys()) == {"by", "resources", "thread_content", "file_content"}
	assert result["by"] is None


@pytest.mark.asyncio
async def test_search_revectorize_requires_admin(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = cast("dict[str, str]", user_auth["headers"])
	get_response = await client.get("/v1/search/revectorize", headers=headers)
	post_response = await client.post("/v1/search/revectorize", headers=headers)
	assert get_response.status_code == 403
	assert post_response.status_code == 403


# merged vectorize_X(session, ids) semantics


@pytest.mark.asyncio
async def test_vectorize_notes_ids_semantics(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""ids=[] is a no-op; ids targets exactly those rows; ids=None takes all
	eligible rows and excludes deleted ones."""
	from api.v1.service import notes as notes_service

	s = uuid4().hex[:8]
	user = User(
		email=f"vn_{s}@rvz.test",
		username=f"vn_{s}",
		hashed_password=hash_password("x"),
		is_active=True,
	)
	db_session.add(user)
	await db_session.flush()
	note_a = Note(user_id=str(user.id), title=f"a_{s}", content="alpha")
	note_b = Note(user_id=str(user.id), title=f"b_{s}", content="bravo")
	note_deleted = Note(user_id=str(user.id), title=f"d_{s}", content="gone")
	note_deleted.deleted_at = datetime.now(tz=UTC)
	db_session.add_all([note_a, note_b, note_deleted])
	await db_session.flush()

	batches: list[list[str]] = []

	async def _capture(notes: list[Note], session: object) -> int:
		batches.append(sorted(str(n.id) for n in notes))
		return len(notes)

	monkeypatch.setattr(notes_service, "_vectorize_notes", _capture)

	assert await notes_service.vectorize_notes(db_session, ids=[]) == 0
	assert batches == []

	assert await notes_service.vectorize_notes(db_session, ids=[note_a.id]) == 1
	assert batches == [[str(note_a.id)]]

	# deleted rows are skipped even when explicitly targeted.
	batches.clear()
	await notes_service.vectorize_notes(db_session, ids=[note_deleted.id])
	assert batches == [[]]

	batches.clear()
	await notes_service.vectorize_notes(db_session)
	assert len(batches) == 1
	assert str(note_a.id) in batches[0]
	assert str(note_b.id) in batches[0]
	assert str(note_deleted.id) not in batches[0]


@pytest.mark.asyncio
async def test_vectorize_memories_ids_semantics(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service import memories as memories_service

	s = uuid4().hex[:8]
	user = User(
		email=f"vm_{s}@rvz.test",
		username=f"vm_{s}",
		hashed_password=hash_password("x"),
		is_active=True,
	)
	db_session.add(user)
	await db_session.flush()
	memory = Memory(user_id=user.id, content=f"remember {s}")
	db_session.add(memory)
	await db_session.flush()

	batches: list[list[str]] = []

	async def _capture(
		spec: object, resources: list[Memory], session: object, **kwargs: object
	) -> int:
		_ = (spec, session, kwargs)
		batches.append([str(m.id) for m in resources])
		return len(resources)

	monkeypatch.setattr(memories_service, "vectorize_resources", _capture)

	assert await memories_service.vectorize_memories(db_session, ids=[]) == 0
	assert batches == []
	await memories_service.vectorize_memories(db_session, ids=[memory.id])
	assert batches == [[str(memory.id)]]
