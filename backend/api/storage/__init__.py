"""file storage backend registry.

backends are registered at application startup via the app lifespan
(see api/main.py) and accessed by name throughout the process lifetime.

each File record's storage_backend column references the backend name
used at write time, so changing the default does not break old records.
"""

from __future__ import annotations

import logging

from api.storage.base import FileInfo, MimeType, StorageBackend
from api.storage.local import LocalStorageBackend
from api.storage.s3 import S3StorageBackend


log = logging.getLogger(__name__)

_BACKENDS: dict[str, StorageBackend] = {}


def register(name: str, backend: StorageBackend) -> None:
	"""register a backend instance under a name.

	call this at app startup before any storage operations.
	registering the same name twice replaces the previous instance.
	"""
	_BACKENDS[name] = backend
	log.info("registered storage backend: %s", name)


def get_storage_backend(name: str) -> StorageBackend:
	"""return a registered backend by name.

	raises ValueError if the backend has not been registered.
	"""
	try:
		return _BACKENDS[name]
	except KeyError:
		registered = list(_BACKENDS)
		raise ValueError(
			f"storage backend not registered: {name!r}. "
			f"registered backends: {registered}"
		) from None


async def close_all() -> None:
	"""close all registered backends. wire to app shutdown lifespan."""
	for name, backend in list(_BACKENDS.items()):
		log.info("closing storage backend: %s", name)
		await backend.close()
	_BACKENDS.clear()


__all__ = [
	"FileInfo",
	"LocalStorageBackend",
	"MimeType",
	"S3StorageBackend",
	"StorageBackend",
	"close_all",
	"get_storage_backend",
	"register",
]
