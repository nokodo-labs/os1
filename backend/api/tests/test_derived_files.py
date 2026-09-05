"""tests for generic derived files and the thumbnail stub."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File, FileSource, FileStatus
from api.models.user import User
from api.schemas.user import UserCreate
from api.storage.base import FileInfo, MimeType, StorageBackend
from api.v1.service import users as user_service
from api.v1.service.files import derived_files as derived_files_service
from api.v1.service.files.derived_files import (
	delete_all_derived_file_bytes,
	find_derived_file,
	has_derived_file,
	read_derived_file_bytes,
	write_derived_file,
)
from api.v1.service.files.thumbnails import (
	can_generate_thumbnail,
	generate_thumbnail_bytes,
	store_thumbnail,
)
from nokodo_ai.utils.typeid import TypeID, new_typeid


class _DictStorageBackend(StorageBackend):
	def __init__(self) -> None:
		super().__init__("memory")
		self.objects: dict[str, bytes] = {}
		self.deleted: list[str] = []

	async def put(
		self, key: str, data: bytes | AsyncIterator[bytes], content_type: MimeType
	) -> None:
		assert isinstance(data, bytes)
		self.objects[key] = data

	async def get(self, key: str) -> AsyncIterator[bytes]:
		return _single(self.objects[key])

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


async def _single(data: bytes) -> AsyncIterator[bytes]:
	yield data


async def _user(db_session: AsyncSession, slug: str) -> User:
	return await user_service.create_user(
		UserCreate(
			email=f"{slug}@example.com",
			username=slug,
			password="password123",
			is_superuser=True,
		),
		db_session,
	)


async def _origin(db_session: AsyncSession, owner_id: object, mime: str) -> File:
	file = File(
		id=TypeID(new_typeid("file")),
		owner_id=owner_id,
		source=FileSource.USER_UPLOADED,
		storage_backend="memory",
		storage_key=f"tests/{new_typeid('file')}",
		filename="report.bin",
		mime_type=mime,
		size_bytes=10,
		status=FileStatus.AVAILABLE,
	)
	db_session.add(file)
	await db_session.flush()
	return file


async def test_write_find_read_round_trip(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _user(db_session, "df_round")
	origin = await _origin(db_session, user.id, "image/png")

	child = await write_derived_file(
		origin,
		FileSource.THUMBNAIL,
		b"thumb-bytes",
		"image/webp",
		"thumbnail",
		db_session,
	)

	assert child.parent_file_id == str(origin.id)
	assert child.source == FileSource.THUMBNAIL
	assert child.owner_id is None
	assert await has_derived_file(origin.id, FileSource.THUMBNAIL, db_session)
	got = await read_derived_file_bytes(origin.id, FileSource.THUMBNAIL, db_session)
	assert got == b"thumb-bytes"


async def test_write_reuses_row_per_source(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _user(db_session, "df_reuse")
	origin = await _origin(db_session, user.id, "image/png")

	first = await write_derived_file(
		origin, FileSource.THUMBNAIL, b"v1", "image/webp", "thumbnail", db_session
	)
	first_key = first.storage_key
	second = await write_derived_file(
		origin, FileSource.THUMBNAIL, b"v2", "image/webp", "thumbnail", db_session
	)

	assert second.id == first.id
	assert second.storage_key != first_key
	assert first_key in backend.deleted
	got = await read_derived_file_bytes(origin.id, FileSource.THUMBNAIL, db_session)
	assert got == b"v2"


async def test_distinct_sources_coexist_for_one_parent(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _user(db_session, "df_coexist")
	origin = await _origin(db_session, user.id, "image/png")

	await write_derived_file(
		origin,
		FileSource.TEXT_EXTRACTION,
		b"text",
		"text/plain",
		"extracted",
		db_session,
	)
	await write_derived_file(
		origin, FileSource.THUMBNAIL, b"thumb", "image/webp", "thumbnail", db_session
	)

	text_child = await find_derived_file(
		origin.id, FileSource.TEXT_EXTRACTION, db_session
	)
	thumb_child = await find_derived_file(origin.id, FileSource.THUMBNAIL, db_session)
	assert text_child is not None
	assert thumb_child is not None
	assert text_child.id != thumb_child.id


async def test_delete_all_derived_file_bytes_clears_every_kind(
	monkeypatch, db_session: AsyncSession
) -> None:
	backend = _DictStorageBackend()
	monkeypatch.setattr(
		derived_files_service, "get_storage_backend", lambda _n: backend
	)
	user = await _user(db_session, "df_delall")
	origin = await _origin(db_session, user.id, "image/png")
	text_child = await write_derived_file(
		origin,
		FileSource.TEXT_EXTRACTION,
		b"text",
		"text/plain",
		"extracted",
		db_session,
	)
	thumb_child = await write_derived_file(
		origin, FileSource.THUMBNAIL, b"thumb", "image/webp", "thumbnail", db_session
	)

	await delete_all_derived_file_bytes(origin.id, db_session)

	# both kinds' bytes are dropped, not just one.
	assert text_child.storage_key in backend.deleted
	assert thumb_child.storage_key in backend.deleted


# thumbnail stub


def test_can_generate_thumbnail_gate() -> None:
	def f(mime: str, name: str) -> File:
		return File(
			id=TypeID(new_typeid("file")),
			owner_id=new_typeid("user"),
			source=FileSource.USER_UPLOADED,
			storage_backend="memory",
			storage_key="k",
			filename=name,
			mime_type=mime,
			status=FileStatus.AVAILABLE,
		)

	assert can_generate_thumbnail(f("image/png", "a.png")) is True
	assert can_generate_thumbnail(f("video/mp4", "a.mp4")) is True
	assert can_generate_thumbnail(f("application/pdf", "a.pdf")) is True
	assert can_generate_thumbnail(f("audio/mpeg", "a.mp3")) is False
	assert can_generate_thumbnail(f("text/plain", "a.txt")) is False


async def test_store_thumbnail_noops_for_non_thumbnailable(
	db_session: AsyncSession,
) -> None:
	user = await _user(db_session, "thumb_noop")
	origin = await _origin(db_session, user.id, "audio/mpeg")
	# returns None without invoking the (unimplemented) generator.
	assert await store_thumbnail(origin, db_session) is None


async def test_generate_thumbnail_bytes_not_implemented(
	db_session: AsyncSession,
) -> None:
	user = await _user(db_session, "thumb_gen")
	origin = await _origin(db_session, user.id, "image/png")
	with pytest.raises(NotImplementedError):
		await generate_thumbnail_bytes(origin, db_session)
