"""main fastapi application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api.boot_settings import boot_settings
from api.constants import API_V1_MOUNT_PATH
from api.database import init_db
from api.exceptions import (
	unhandled_exception_handler,
	validation_exception_handler,
)
from api.logging import configure_logging, get_logger
from api.middleware import (
	RequestIDMiddleware,
	RequestLoggingMiddleware,
	SecurityHeadersMiddleware,
)
from api.routers import system as system_router
from api.runtime import configure_psycopg_asyncio_event_loop_policy
from api.settings import settings
from api.storage import close_all as close_storage
from api.storage import register as register_storage
from api.storage.local import LocalStorageBackend
from api.storage.s3 import S3StorageBackend
from api.v1.app import v1_app


configure_psycopg_asyncio_event_loop_policy()

# configure logging early, before anything else logs
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
	"""application lifespan events."""
	logger.info(
		"starting %s v%s [%s]",
		settings.branding.site_name,
		settings.branding.app_version,
		boot_settings.ENV,
	)

	# startup: skip db init during tests
	if not boot_settings.TESTING:
		await init_db()

	# register the configured storage backend
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
		register_storage("s3", s3)
	else:
		register_storage(
			"local", LocalStorageBackend(root_path=storage_cfg.local.root_path)
		)

	logger.info("startup complete")
	yield

	# shutdown
	logger.info("shutting down")
	await close_storage()


app = FastAPI(
	title=settings.branding.site_name,
	version=settings.branding.app_version,
	lifespan=lifespan,
)

# middleware stack (executed in reverse order of addition)
# 5. request id (outermost - runs first)
app.add_middleware(RequestIDMiddleware)

# 4. security headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. request logging
app.add_middleware(RequestLoggingMiddleware)

# 1. cors (closest to app)
app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.security.cors_origins,
	allow_origin_regex="|".join(
		f"({pattern})" for pattern in settings.security.cors_origins_regex
	),
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
	"""API root with information and links."""
	return {
		"name": settings.branding.site_name,
		"version": settings.branding.app_version,
		"api_version": "v1",
		"docs": "/v1/docs",
		"openapi": "/v1/openapi.json",
		"health": "/health",
	}


@app.get("/health")
async def health_check() -> dict[str, str]:
	"""Health check endpoint."""
	return {"status": "healthy"}


# Non-versioned routes
app.include_router(system_router.router)


# Mount API v1
app.mount(API_V1_MOUNT_PATH, v1_app)
