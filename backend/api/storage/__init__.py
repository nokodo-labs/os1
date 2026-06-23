"""file storage backend registry.

backends are registered at process startup and accessed by name throughout
the process lifetime.

each File record's storage_backend column references the backend name
used at write time, so changing the default does not break old records.
"""

from __future__ import annotations

import logging

from api.settings import settings
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


async def configure_storage_backends() -> None:
	"""register the configured storage backend for this process."""
	storage_cfg = settings.assets.storage
	if storage_cfg.backend == "s3":
		s3 = S3StorageBackend(
			bucket=storage_cfg.s3.bucket,
			region=storage_cfg.s3.region,
			endpoint_url=storage_cfg.s3.endpoint_url,
			access_key_id=storage_cfg.s3.access_key_id,
			secret_access_key=storage_cfg.s3.secret_access_key,
			prefix=storage_cfg.s3.prefix,
			presigned_url_ttl=storage_cfg.s3.presigned_url_ttl,
			multipart_threshold=storage_cfg.s3.multipart_threshold,
			multipart_chunk_size=storage_cfg.s3.multipart_chunk_size,
			max_retries=storage_cfg.s3.max_retries,
			retry_mode=storage_cfg.s3.retry_mode,
		)
		await s3.ensure_bucket()
		register("s3", s3)
		return
	register("local", LocalStorageBackend(root_path=storage_cfg.local.root_path))


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
	"configure_storage_backends",
	"get_storage_backend",
	"register",
]
