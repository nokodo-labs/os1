"""file storage backend registry.

every configured backend is registered at process startup and accessed by
name throughout the process lifetime.

each File record's storage_backend column references the backend name
used at write time, so changing the active backend does not break old
records: their backend stays registered and keeps serving them.
"""

import logging
import uuid

from api.settings import (
	LocalStorageBackendConfig,
	StorageBackendConfig,
	settings,
)
from api.storage.base import FileInfo, MimeType, StorageBackend
from api.storage.local import LocalStorageBackend
from api.storage.s3 import S3StorageBackend


log = logging.getLogger(__name__)

_BACKENDS: dict[str, StorageBackend] = {}


def new_storage_key(prefix: str | None = None) -> str:
	"""generate a fresh opaque storage key for a stored object.

	uses a uuid v7 hex string (time-ordered, globally unique), independent of
	the file's db id so ownership changes and re-keys never move bytes. an
	optional prefix enables storage lifecycle rules (e.g. an s3 'tmp/' expiry
	rule) without embedding ownership semantics in the path.
	"""
	key = uuid.uuid7().hex
	if prefix:
		return f"{prefix.rstrip('/')}/{key}"
	return key


def register(name: str, backend: StorageBackend) -> None:
	"""register a backend instance under a name.

	call this at app startup before any storage operations.
	registering the same name twice replaces the previous instance.
	"""
	_BACKENDS[name] = backend
	log.info("registered storage backend: %s", name)


def _build_backend(config: StorageBackendConfig) -> StorageBackend:
	"""instantiate the backend a config describes."""
	if isinstance(config, LocalStorageBackendConfig):
		return LocalStorageBackend(
			name=config.name,
			root_path=config.root_path,
		)
	return S3StorageBackend(
		name=config.name,
		bucket=config.bucket,
		region=config.region,
		endpoint_url=config.endpoint_url,
		access_key_id=config.access_key_id,
		secret_access_key=config.secret_access_key,
		prefix=config.prefix,
		presigned_url_ttl=config.presigned_url_ttl,
		multipart_threshold=config.multipart_threshold,
		multipart_chunk_size=config.multipart_chunk_size,
		max_retries=config.max_retries,
		retry_mode=config.retry_mode,
	)


async def configure_storage_backends() -> None:
	"""register every configured storage backend for this process.

	replaces the previous registration set, so a settings change adds, drops
	and re-points backends in one pass.
	"""
	previous = dict(_BACKENDS)
	_BACKENDS.clear()
	for config in settings.assets.storage.backends:
		backend = _build_backend(config)
		if isinstance(backend, S3StorageBackend):
			await backend.ensure_bucket()
		register(config.name, backend)
	for name, backend in previous.items():
		log.info("closing storage backend: %s", name)
		await backend.close()


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
	"new_storage_key",
	"register",
]
