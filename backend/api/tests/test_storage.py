"""tests for file storage backends and registry."""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from api.storage import _BACKENDS, close_all, get_storage_backend, register
from api.storage.base import FileInfo, StorageBackend
from api.storage.local import LocalStorageBackend


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


async def _collect(stream: AsyncIterator[bytes]) -> bytes:
	"""collect an async iterator into bytes."""
	parts: list[bytes] = []
	async for chunk in stream:
		parts.append(chunk)
	return b"".join(parts)


# ---------------------------------------------------------------------------
# FileInfo dataclass
# ---------------------------------------------------------------------------


class TestFileInfo:
	def test_frozen(self) -> None:
		info = FileInfo(size=100, content_type="text/plain", last_modified=None)
		with pytest.raises(AttributeError):
			info.size = 200  # type: ignore[misc]

	def test_fields(self) -> None:
		info = FileInfo(size=42, content_type="image/png", last_modified=None)
		assert info.size == 42
		assert info.content_type == "image/png"
		assert info.last_modified is None

	def test_optional_fields_default_none(self) -> None:
		info = FileInfo(size=1, content_type=None, last_modified=None)
		assert info.etag is None
		assert info.checksum_sha256 is None

	def test_optional_fields_set(self) -> None:
		info = FileInfo(
			size=10,
			content_type="text/plain",
			last_modified=None,
			etag='"abc123"',
			checksum_sha256="deadbeef" * 8,
		)
		assert info.etag == '"abc123"'
		assert info.checksum_sha256 == "deadbeef" * 8


# ---------------------------------------------------------------------------
# StorageBackend ABC
# ---------------------------------------------------------------------------


class TestStorageBackendABC:
	def test_cannot_instantiate(self) -> None:
		with pytest.raises(TypeError):
			StorageBackend(name="test")  # type: ignore[abstract]

	async def test_close_is_noop_by_default(self) -> None:
		"""concrete close() should be callable without error."""

		class Stub(StorageBackend):
			async def put(
				self,
				key: str,
				data: bytes | AsyncIterator[bytes],
				content_type: str | None,
			) -> None:
				pass

			async def get(self, key: str) -> AsyncIterator[bytes]:  # type: ignore[override, misc]
				yield b""

			async def delete(self, key: str) -> None:
				pass

			async def exists(self, key: str) -> bool:
				return False

			async def stat(self, key: str) -> FileInfo | None:
				return None

			async def copy(self, src_key: str, dst_key: str) -> None:
				pass

			async def get_url(
				self, key: str, expires_in: int | None = None
			) -> str | None:
				return None

		stub = Stub(name="stub")
		await stub.close()  # should not raise

	async def test_checksum_sha256_default_impl(self) -> None:
		"""default checksum implementation streams via get()."""
		payload = b"hello world"
		expected = _sha256(payload)

		class Stub(StorageBackend):
			async def put(
				self,
				key: str,
				data: bytes | AsyncIterator[bytes],
				content_type: str | None,
			) -> None:
				pass

			async def get(self, key: str) -> AsyncIterator[bytes]:
				async def _gen() -> AsyncGenerator[bytes]:
					yield payload

				return _gen()

			async def delete(self, key: str) -> None:
				pass

			async def exists(self, key: str) -> bool:
				return True

			async def stat(self, key: str) -> FileInfo | None:
				return None

			async def copy(self, src_key: str, dst_key: str) -> None:
				pass

			async def get_url(
				self, key: str, expires_in: int | None = None
			) -> str | None:
				return None

		stub = Stub(name="stub")
		result = await stub.checksum_sha256("any-key")
		assert result == expected


# ---------------------------------------------------------------------------
# LocalStorageBackend
# ---------------------------------------------------------------------------


@pytest.fixture()
def local_root(tmp_path: Path) -> Path:
	"""temporary directory for local backend tests."""
	return tmp_path / "storage"


@pytest.fixture()
def local_backend(local_root: Path) -> LocalStorageBackend:
	return LocalStorageBackend(root_path=str(local_root))


class TestLocalStorageBackend:
	async def test_put_and_get_bytes(self, local_backend: LocalStorageBackend) -> None:
		payload = b"hello storage"
		await local_backend.put("test/file.bin", payload, "application/octet-stream")
		result = await _collect(await local_backend.get("test/file.bin"))
		assert result == payload

	async def test_put_and_get_stream(self, local_backend: LocalStorageBackend) -> None:
		chunks = [b"chunk1", b"chunk2", b"chunk3"]

		async def stream() -> AsyncGenerator[bytes]:
			for c in chunks:
				yield c

		await local_backend.put("streamed.bin", stream(), "application/octet-stream")
		result = await _collect(await local_backend.get("streamed.bin"))
		assert result == b"chunk1chunk2chunk3"

	async def test_exists(self, local_backend: LocalStorageBackend) -> None:
		assert not await local_backend.exists("nope")
		await local_backend.put("yes.txt", b"y", "text/plain")
		assert await local_backend.exists("yes.txt")

	async def test_delete(self, local_backend: LocalStorageBackend) -> None:
		await local_backend.put("del.txt", b"x", "text/plain")
		assert await local_backend.exists("del.txt")
		await local_backend.delete("del.txt")
		assert not await local_backend.exists("del.txt")

	async def test_delete_missing_noop(
		self, local_backend: LocalStorageBackend
	) -> None:
		await local_backend.delete("does-not-exist")

	async def test_stat(self, local_backend: LocalStorageBackend) -> None:
		payload = b"stat me"
		await local_backend.put("stat.txt", payload, "text/plain")
		info = await local_backend.stat("stat.txt")
		assert info is not None
		assert info.size == len(payload)
		assert info.content_type == "text/plain"
		assert info.last_modified is not None

	async def test_stat_missing(self, local_backend: LocalStorageBackend) -> None:
		assert await local_backend.stat("no-file") is None

	async def test_copy(self, local_backend: LocalStorageBackend) -> None:
		payload = b"copy me"
		await local_backend.put("src.bin", payload, "application/octet-stream")
		await local_backend.copy("src.bin", "dst.bin")
		result = await _collect(await local_backend.get("dst.bin"))
		assert result == payload
		# sidecar should also be copied
		info = await local_backend.stat("dst.bin")
		assert info is not None
		assert info.content_type == "application/octet-stream"

	async def test_get_url_returns_none(
		self, local_backend: LocalStorageBackend
	) -> None:
		assert await local_backend.get_url("anything") is None

	async def test_checksum_sha256(self, local_backend: LocalStorageBackend) -> None:
		payload = b"checksum me"
		await local_backend.put("hash.bin", payload, "application/octet-stream")
		result = await local_backend.checksum_sha256("hash.bin")
		assert result == _sha256(payload)

	async def test_checksum_missing_file(
		self, local_backend: LocalStorageBackend
	) -> None:
		with pytest.raises(FileNotFoundError):
			await local_backend.checksum_sha256("no-such-file")

	async def test_get_missing_file_raises(
		self, local_backend: LocalStorageBackend
	) -> None:
		with pytest.raises(FileNotFoundError):
			await local_backend.get("no-such-file")

	async def test_path_traversal_rejected(
		self, local_backend: LocalStorageBackend
	) -> None:
		with pytest.raises(ValueError, match="escapes root"):
			await local_backend.put("../escape.txt", b"bad", "text/plain")

	async def test_path_traversal_get(self, local_backend: LocalStorageBackend) -> None:
		with pytest.raises(ValueError, match="escapes root"):
			await local_backend.get("../../etc/passwd")

	async def test_nested_keys(self, local_backend: LocalStorageBackend) -> None:
		await local_backend.put("a/b/c/deep.txt", b"deep", "text/plain")
		result = await _collect(await local_backend.get("a/b/c/deep.txt"))
		assert result == b"deep"

	async def test_overwrite(self, local_backend: LocalStorageBackend) -> None:
		await local_backend.put("over.txt", b"v1", "text/plain")
		await local_backend.put("over.txt", b"v2", "text/plain")
		result = await _collect(await local_backend.get("over.txt"))
		assert result == b"v2"

	async def test_meta_sidecar_content_type(
		self, local_backend: LocalStorageBackend
	) -> None:
		await local_backend.put("typed.json", b"{}", "application/json")
		info = await local_backend.stat("typed.json")
		assert info is not None
		assert info.content_type == "application/json"

	async def test_stat_without_meta_sidecar(
		self, local_backend: LocalStorageBackend, local_root: Path
	) -> None:
		"""stat returns None content_type when .meta sidecar is missing."""
		await local_backend.put("no_meta.bin", b"x", "application/octet-stream")
		# remove the sidecar
		meta = local_root / "no_meta.bin.meta"
		if meta.exists():
			meta.unlink()
		info = await local_backend.stat("no_meta.bin")
		assert info is not None
		assert info.content_type is None

	async def test_large_file_stream(self, local_backend: LocalStorageBackend) -> None:
		"""verify streaming works for files larger than chunk size."""
		# 512 KB file (larger than _CHUNK_SIZE of 256 KB)
		payload = os.urandom(512 * 1024)
		await local_backend.put("large.bin", payload, "application/octet-stream")
		result = await _collect(await local_backend.get("large.bin"))
		assert result == payload
		assert await local_backend.checksum_sha256("large.bin") == _sha256(payload)

	async def test_put_error_cleans_up_temp(
		self, local_backend: LocalStorageBackend
	) -> None:
		"""verify temp file is cleaned up on write error."""

		async def bad_stream() -> AsyncGenerator[bytes]:
			yield b"some data"
			raise RuntimeError("write failed")

		with pytest.raises(RuntimeError, match="write failed"):
			await local_backend.put("fail.bin", bad_stream(), "text/plain")

		# file should not exist
		assert not await local_backend.exists("fail.bin")


# ---------------------------------------------------------------------------
# storage registry
# ---------------------------------------------------------------------------


class TestStorageRegistry:
	"""registry tests isolate the global _BACKENDS dict by save/restore."""

	@pytest.fixture(autouse=True)
	def _isolate(self) -> Generator[None]:

		saved = dict(_BACKENDS)
		_BACKENDS.clear()
		try:
			yield
		finally:
			_BACKENDS.clear()
			_BACKENDS.update(saved)

	def test_register_and_get(self, local_root: Path) -> None:
		"""register a backend then retrieve it by name."""

		backend = LocalStorageBackend(root_path=str(local_root))
		register("local", backend)

		assert get_storage_backend("local") is backend
		assert backend.name == "local"

	def test_register_twice_replaces(self, local_root: Path) -> None:
		"""registering the same name replaces the previous instance."""

		a = LocalStorageBackend(root_path=str(local_root / "a"))
		b = LocalStorageBackend(root_path=str(local_root / "b"))
		register("local", a)
		register("local", b)

		assert get_storage_backend("local") is b

	def test_unregistered_backend_raises(self) -> None:
		"""get_storage_backend raises ValueError for unknown names."""

		with pytest.raises(ValueError, match="not registered"):
			get_storage_backend("nonexistent")

	async def test_close_all(self) -> None:
		"""close_all calls close() on every backend and empties the registry."""

		mock_backend = AsyncMock(spec=StorageBackend)
		mock_backend.name = "mock"
		_BACKENDS["mock"] = mock_backend

		await close_all()
		mock_backend.close.assert_awaited_once()
		assert len(_BACKENDS) == 0
