"""local filesystem storage backend."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from api.storage.base import FileInfo, MimeType, StorageBackend


_CHUNK_SIZE = 256 * 1024  # 256 KB read/hash chunks


class LocalStorageBackend(StorageBackend):
	"""stores files on the local filesystem under a configurable root.

	content-type is persisted in a .meta sidecar file next to the data file
	so stat() can return it without a database lookup.

	writes use atomic rename (write to temp, then os.replace) to prevent
	corruption under concurrent workers.
	"""

	def __init__(self, root_path: str) -> None:
		super().__init__(name="local")
		self._root = Path(root_path)

	def _resolve(self, key: str) -> Path:
		"""resolve a storage key to an absolute path.

		rejects path traversal attempts (keys containing .. or absolute
		components) to keep all writes confined under the root.
		"""
		resolved = (self._root / key).resolve()
		root_resolved = self._root.resolve()
		if not resolved.is_relative_to(root_resolved):
			raise ValueError(f"storage key escapes root directory: {key!r}")
		return resolved

	def _meta_path(self, key: str) -> Path:
		resolved = self._resolve(key)
		return resolved.with_suffix(resolved.suffix + ".meta")

	# -- interface --

	async def put(
		self,
		key: str,
		data: bytes | AsyncIterator[bytes],
		content_type: MimeType,
	) -> None:
		target = self._resolve(key)
		await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)

		# atomic write: temp file in same dir, then rename
		fd, tmp = tempfile.mkstemp(dir=str(target.parent))
		try:
			if isinstance(data, (bytes, bytearray, memoryview)):
				await asyncio.to_thread(os.write, fd, data)
			else:
				async for chunk in data:
					await asyncio.to_thread(os.write, fd, chunk)
			await asyncio.to_thread(os.close, fd)
			fd = -1  # mark as closed so the except block doesn't double-close
			await asyncio.to_thread(os.replace, tmp, str(target))
		except BaseException:
			if fd >= 0:
				with contextlib.suppress(OSError):
					await asyncio.to_thread(os.close, fd)
			with contextlib.suppress(OSError):
				await asyncio.to_thread(os.unlink, tmp)
			raise

		# write content-type sidecar
		meta = self._meta_path(key)
		await asyncio.to_thread(meta.write_text, content_type, encoding="utf-8")

	async def get(self, key: str) -> AsyncIterator[bytes]:
		path = self._resolve(key)
		if not await asyncio.to_thread(path.exists):
			raise FileNotFoundError(f"storage key not found: {key}")
		return _stream_file(path)

	async def delete(self, key: str) -> None:
		path = self._resolve(key)
		meta = self._meta_path(key)
		for p in (path, meta):
			with contextlib.suppress(FileNotFoundError):
				await asyncio.to_thread(p.unlink)

	async def exists(self, key: str) -> bool:
		return await asyncio.to_thread(self._resolve(key).exists)

	async def stat(self, key: str) -> FileInfo | None:
		path = self._resolve(key)
		try:
			st = await asyncio.to_thread(path.stat)
		except FileNotFoundError:
			return None

		content_type: MimeType | None = None
		meta = self._meta_path(key)
		try:
			content_type = await asyncio.to_thread(meta.read_text, encoding="utf-8")
		except FileNotFoundError:
			pass

		return FileInfo(
			size=st.st_size,
			content_type=content_type,
			last_modified=datetime.fromtimestamp(st.st_mtime, tz=UTC),
		)

	async def copy(self, src_key: str, dst_key: str) -> None:
		src = self._resolve(src_key)
		dst = self._resolve(dst_key)
		await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)
		await asyncio.to_thread(shutil.copy2, src, dst)
		# copy sidecar too
		src_meta = self._meta_path(src_key)
		if await asyncio.to_thread(src_meta.exists):
			dst_meta = self._meta_path(dst_key)
			await asyncio.to_thread(shutil.copy2, src_meta, dst_meta)

	async def get_url(self, key: str, expires_in: int | None = None) -> str | None:
		# local backend does not support direct URLs
		return None

	async def checksum_sha256(self, key: str) -> str:
		"""compute SHA-256 directly from disk without the get() indirection."""
		path = self._resolve(key)
		if not await asyncio.to_thread(path.exists):
			raise FileNotFoundError(f"storage key not found: {key}")

		def _hash() -> str:
			h = hashlib.sha256()
			with open(path, "rb") as f:
				while chunk := f.read(_CHUNK_SIZE):
					h.update(chunk)
			return h.hexdigest()

		return await asyncio.to_thread(_hash)


# -- module-level helpers --


async def _stream_file(path: Path) -> AsyncIterator[bytes]:
	"""yield file contents in chunks via the thread pool."""
	fd = await asyncio.to_thread(open, path, "rb")
	try:
		while True:
			chunk = await asyncio.to_thread(fd.read, _CHUNK_SIZE)
			if not chunk:
				break
			yield chunk
	finally:
		await asyncio.to_thread(fd.close)
