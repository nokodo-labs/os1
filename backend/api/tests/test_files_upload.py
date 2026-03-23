"""integration tests for file upload, download, and CRUD endpoints."""

from __future__ import annotations

import hashlib
import io
import os
from collections.abc import AsyncGenerator, AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import FileSource, FileStatus
from api.storage import get_storage_backend
from api.v1.service.files import delete_content, read_content, store_file
from nokodo_ai.utils.typeid import new_typeid


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


class TestUploadFile:
	async def test_upload_basic(self, client: AsyncClient, admin_auth: dict) -> None:
		headers = admin_auth["headers"]
		payload = b"hello upload"
		resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("test.txt", io.BytesIO(payload), "text/plain")},
		)
		assert resp.status_code == 201
		body = resp.json()
		assert body["filename"] == "test.txt"
		assert body["mime_type"] == "text/plain"
		assert body["status"] == FileStatus.AVAILABLE
		assert body["source"] == FileSource.UPLOAD
		assert body["size_bytes"] == len(payload)
		assert body["checksum_sha256"] == _sha256(payload)
		assert body["storage_backend"] == "local"
		assert body["storage_key"]  # non-empty

	async def test_upload_with_project(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		# create a project first
		proj_resp = await client.post(
			"/v1/projects",
			headers=headers,
			json={"name": "upload-proj"},
		)
		assert proj_resp.status_code == 201
		project_id = proj_resp.json()["id"]

		payload = b"project file"
		resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("proj.txt", io.BytesIO(payload), "text/plain")},
			data={"project_ids": project_id},
		)
		assert resp.status_code == 201
		body = resp.json()
		assert project_id in body["project_ids"]

	async def test_upload_custom_source(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={
				"file": ("gen.bin", io.BytesIO(b"data"), "application/octet-stream")
			},
			data={"source": "generated"},
		)
		assert resp.status_code == 201
		assert resp.json()["source"] == FileSource.GENERATED

	async def test_upload_unauthenticated(self, client: AsyncClient) -> None:
		resp = await client.post(
			"/v1/files/upload",
			files={"file": ("x.txt", io.BytesIO(b"nope"), "text/plain")},
		)
		assert resp.status_code == 401

	async def test_upload_binary_file(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		payload = b"\x00\x01\x02\xff" * 1024
		resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={
				"file": ("binary.bin", io.BytesIO(payload), "application/octet-stream")
			},
		)
		assert resp.status_code == 201
		body = resp.json()
		assert body["size_bytes"] == len(payload)
		assert body["checksum_sha256"] == _sha256(payload)


# ---------------------------------------------------------------------------
# download / content
# ---------------------------------------------------------------------------


class TestFileContent:
	async def test_download_uploaded_file(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		payload = b"download me"
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("dl.txt", io.BytesIO(payload), "text/plain")},
		)
		assert upload_resp.status_code == 201
		file_id = upload_resp.json()["id"]

		resp = await client.get(f"/v1/files/{file_id}/content", headers=headers)
		assert resp.status_code == 200
		assert resp.content == payload
		assert "text/plain" in resp.headers.get("content-type", "")
		assert "dl.txt" in resp.headers.get("content-disposition", "")

	async def test_download_nonexistent_file(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		fake_id = new_typeid("file")
		resp = await client.get(f"/v1/files/{fake_id}/content", headers=headers)
		assert resp.status_code in {403, 404}

	async def test_download_unauthenticated(self, client: AsyncClient) -> None:
		fake_id = new_typeid("file")
		resp = await client.get(f"/v1/files/{fake_id}/content")
		assert resp.status_code == 401


# ---------------------------------------------------------------------------
# url endpoint
# ---------------------------------------------------------------------------


class TestFileUrl:
	async def test_url_local_backend_returns_null(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		payload = b"url test"
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("url.txt", io.BytesIO(payload), "text/plain")},
		)
		assert upload_resp.status_code == 201
		file_id = upload_resp.json()["id"]

		resp = await client.get(f"/v1/files/{file_id}/url", headers=headers)
		assert resp.status_code == 200
		# local backend returns None for url
		assert resp.json() == {"url": None}

	async def test_url_nonexistent_file(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		fake_id = new_typeid("file")
		resp = await client.get(f"/v1/files/{fake_id}/url", headers=headers)
		assert resp.status_code in {403, 404}


# ---------------------------------------------------------------------------
# CRUD - list, get, update, delete
# ---------------------------------------------------------------------------


class TestFileCRUD:
	async def test_list_files_empty(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		resp = await client.get("/v1/files", headers=headers)
		assert resp.status_code == 200
		assert resp.json() == []

	async def test_list_files_after_upload(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("list.txt", io.BytesIO(b"listed"), "text/plain")},
		)
		resp = await client.get("/v1/files", headers=headers)
		assert resp.status_code == 200
		files = resp.json()
		assert len(files) >= 1
		assert any(f["filename"] == "list.txt" for f in files)

	async def test_get_file_by_id(self, client: AsyncClient, admin_auth: dict) -> None:
		headers = admin_auth["headers"]
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("get.txt", io.BytesIO(b"get me"), "text/plain")},
		)
		file_id = upload_resp.json()["id"]
		resp = await client.get(f"/v1/files/{file_id}", headers=headers)
		assert resp.status_code == 200
		assert resp.json()["id"] == file_id
		assert resp.json()["filename"] == "get.txt"

	async def test_update_file_metadata(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("old.txt", io.BytesIO(b"upd"), "text/plain")},
		)
		file_id = upload_resp.json()["id"]
		resp = await client.patch(
			f"/v1/files/{file_id}",
			headers=headers,
			json={"filename": "renamed.txt"},
		)
		assert resp.status_code == 200
		assert resp.json()["filename"] == "renamed.txt"

	async def test_delete_file(self, client: AsyncClient, admin_auth: dict) -> None:
		headers = admin_auth["headers"]
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("del.txt", io.BytesIO(b"gone"), "text/plain")},
		)
		file_id = upload_resp.json()["id"]
		del_resp = await client.delete(f"/v1/files/{file_id}", headers=headers)
		assert del_resp.status_code in {200, 204}

	async def test_delete_nonexistent(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		fake_id = new_typeid("file")
		resp = await client.delete(f"/v1/files/{fake_id}", headers=headers)
		assert resp.status_code in {403, 404}


# ---------------------------------------------------------------------------
# upload then download round-trip
# ---------------------------------------------------------------------------


class TestFileRoundTrip:
	async def test_roundtrip_text(self, client: AsyncClient, admin_auth: dict) -> None:
		headers = admin_auth["headers"]
		original = b"round trip content"
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("rt.txt", io.BytesIO(original), "text/plain")},
		)
		assert upload_resp.status_code == 201
		file_id = upload_resp.json()["id"]

		dl_resp = await client.get(f"/v1/files/{file_id}/content", headers=headers)
		assert dl_resp.status_code == 200
		assert dl_resp.content == original

	async def test_roundtrip_large_binary(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		"""verify a file larger than the chunk size round-trips correctly."""
		headers = admin_auth["headers"]

		original = os.urandom(512 * 1024)  # 512 KB
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={
				"file": (
					"large.bin",
					io.BytesIO(original),
					"application/octet-stream",
				)
			},
		)
		assert upload_resp.status_code == 201
		file_id = upload_resp.json()["id"]

		dl_resp = await client.get(f"/v1/files/{file_id}/content", headers=headers)
		assert dl_resp.status_code == 200
		assert dl_resp.content == original

	async def test_roundtrip_empty_file(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		upload_resp = await client.post(
			"/v1/files/upload",
			headers=headers,
			files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
		)
		assert upload_resp.status_code == 201
		file_id = upload_resp.json()["id"]

		dl_resp = await client.get(f"/v1/files/{file_id}/content", headers=headers)
		assert dl_resp.status_code == 200
		assert dl_resp.content == b""


# ---------------------------------------------------------------------------
# metadata-only create (existing endpoint)
# ---------------------------------------------------------------------------


class TestMetadataCreateFile:
	async def test_create_file_metadata_only(
		self, client: AsyncClient, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		resp = await client.post(
			"/v1/files",
			headers=headers,
			json={
				"storage_backend": "local",
				"storage_key": "manual/key.bin",
				"filename": "manual.bin",
				"source": "import",
			},
		)
		assert resp.status_code == 201
		body = resp.json()
		assert body["storage_backend"] == "local"
		assert body["storage_key"] == "manual/key.bin"
		assert body["status"] == FileStatus.PENDING


# ---------------------------------------------------------------------------
# service-level: store_file, read_content, delete_content
# ---------------------------------------------------------------------------


async def _collect(stream: AsyncIterator[bytes]) -> bytes:
	parts: list[bytes] = []
	async for chunk in stream:
		parts.append(chunk)
	return b"".join(parts)


class TestStoreFile:
	async def test_store_bytes(
		self, db_session: AsyncSession, admin_auth: dict
	) -> None:
		owner_id = admin_auth["user"]["id"]
		payload = b"agent-generated report"
		file = await store_file(
			db_session,
			data=payload,
			owner_id=owner_id,
			filename="report.txt",
			content_type="text/plain",
			source=FileSource.GENERATED,
		)
		assert file.status == FileStatus.AVAILABLE
		assert file.source == FileSource.GENERATED
		assert file.filename == "report.txt"
		assert file.mime_type == "text/plain"
		assert file.size_bytes == len(payload)
		assert file.checksum_sha256 == _sha256(payload)
		assert file.owner_id == owner_id
		assert file.storage_backend is not None
		assert file.storage_key is not None

	async def test_store_stream(
		self, db_session: AsyncSession, admin_auth: dict
	) -> None:
		owner_id = admin_auth["user"]["id"]
		chunks = [b"chunk1", b"chunk2"]

		async def gen() -> AsyncGenerator[bytes]:
			for c in chunks:
				yield c

		file = await store_file(
			db_session,
			data=gen(),
			owner_id=owner_id,
			filename="streamed.bin",
			content_type="application/octet-stream",
		)
		assert file.status == FileStatus.AVAILABLE
		assert file.size_bytes == len(b"chunk1chunk2")

	async def test_store_without_event(
		self, db_session: AsyncSession, admin_auth: dict
	) -> None:
		owner_id = admin_auth["user"]["id"]
		file = await store_file(
			db_session,
			data=b"silent",
			owner_id=owner_id,
			emit_event=False,
		)
		assert file.status == FileStatus.AVAILABLE

	async def test_store_with_project(
		self, client: AsyncClient, db_session: AsyncSession, admin_auth: dict
	) -> None:
		headers = admin_auth["headers"]
		proj_resp = await client.post(
			"/v1/projects",
			headers=headers,
			json={"name": "store-proj"},
		)
		assert proj_resp.status_code == 201
		project_id = proj_resp.json()["id"]

		owner_id = admin_auth["user"]["id"]
		file = await store_file(
			db_session,
			data=b"project file",
			owner_id=owner_id,
			project_ids=[project_id],
		)
		assert project_id in file.project_ids


class TestReadContent:
	async def test_read_stored_file(
		self, db_session: AsyncSession, admin_auth: dict
	) -> None:
		owner_id = admin_auth["user"]["id"]
		payload = b"readable content"
		file = await store_file(
			db_session,
			data=payload,
			owner_id=owner_id,
			content_type="text/plain",
		)
		stream, ct, size = await read_content(file)
		assert await _collect(stream) == payload
		assert ct == "text/plain"
		assert size == len(payload)

	async def test_read_missing_storage_raises(
		self, db_session: AsyncSession, admin_auth: dict
	) -> None:
		owner_id = admin_auth["user"]["id"]
		file = await store_file(
			db_session,
			data=b"will be deleted",
			owner_id=owner_id,
		)
		# manually delete storage object

		backend = get_storage_backend(file.storage_backend)
		await backend.delete(file.storage_key)

		with pytest.raises(FileNotFoundError):
			await read_content(file)


class TestDeleteContent:
	async def test_delete_stored_content(
		self, db_session: AsyncSession, admin_auth: dict
	) -> None:
		owner_id = admin_auth["user"]["id"]
		file = await store_file(
			db_session,
			data=b"deletable",
			owner_id=owner_id,
		)

		backend = get_storage_backend(file.storage_backend)
		assert await backend.exists(file.storage_key)

		await delete_content(file)
		assert not await backend.exists(file.storage_key)

	async def test_delete_missing_does_not_raise(
		self, db_session: AsyncSession, admin_auth: dict
	) -> None:
		owner_id = admin_auth["user"]["id"]
		file = await store_file(
			db_session,
			data=b"gone",
			owner_id=owner_id,
		)

		backend = get_storage_backend(file.storage_backend)
		await backend.delete(file.storage_key)

		# should not raise even though the object is already gone
		await delete_content(file)
