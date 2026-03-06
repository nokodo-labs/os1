"""storage backend abstract interface."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime


type MimeType = str
"""MIME media type string (e.g. ``application/json``, ``image/png``)."""


@dataclass(frozen=True)
class FileInfo:
	"""metadata about a stored file (without downloading it)."""

	size: int
	content_type: MimeType | None
	last_modified: datetime | None
	etag: str | None = None
	checksum_sha256: str | None = None


class StorageBackend(ABC):
	"""abstract base for file storage backends.

	each backend is identified by a unique name that gets persisted in the
	File.storage_backend column so files can be resolved after the default
	backend changes.
	"""

	def __init__(self, name: str) -> None:
		self.name = name

	@abstractmethod
	async def put(
		self,
		key: str,
		data: bytes | AsyncIterator[bytes],
		content_type: MimeType,
	) -> None:
		"""write bytes to storage under the given key."""

	@abstractmethod
	async def get(self, key: str) -> AsyncIterator[bytes]:
		"""stream bytes from storage for the given key."""

	@abstractmethod
	async def delete(self, key: str) -> None:
		"""remove the object at key (no-op if missing)."""

	@abstractmethod
	async def exists(self, key: str) -> bool:
		"""check whether an object exists at key."""

	@abstractmethod
	async def stat(self, key: str) -> FileInfo | None:
		"""return metadata without downloading, or None if missing."""

	@abstractmethod
	async def copy(self, src_key: str, dst_key: str) -> None:
		"""copy an object within the same backend."""

	@abstractmethod
	async def get_url(self, key: str, expires_in: int | None = None) -> str | None:
		"""return a direct/presigned URL, or None if unsupported."""

	async def checksum_sha256(self, key: str) -> str:
		"""compute SHA-256 hex digest by streaming the stored object.

		backends may override this if they can retrieve checksums
		from metadata (e.g. S3 object attributes) without downloading.
		"""
		h = hashlib.sha256()
		async for chunk in await self.get(key):
			h.update(chunk)
		return h.hexdigest()

	async def close(self) -> None:
		"""release resources (sessions, connections). called on shutdown."""
