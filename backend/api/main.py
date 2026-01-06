"""main fastapi application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api.constants import API_V1_MOUNT_PATH
from api.core.config import settings
from api.core.database import init_db
from api.core.exceptions import (
	unhandled_exception_handler,
	validation_exception_handler,
)
from api.core.logging import configure_logging, get_logger
from api.core.runtime import configure_psycopg_asyncio_event_loop_policy
from api.middleware import (
	RequestIDMiddleware,
	RequestLoggingMiddleware,
	SecurityHeadersMiddleware,
)
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
		settings.PROJECT_NAME,
		settings.VERSION,
		settings.APP_ENV,
	)

	# startup: skip db init during tests
	if not settings.TESTING:
		await init_db()

	logger.info("startup complete")
	yield

	# shutdown
	logger.info("shutting down")


app = FastAPI(
	title=settings.PROJECT_NAME,
	version=settings.VERSION,
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
	allow_origins=settings.CORS_ORIGINS,
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
		"name": settings.PROJECT_NAME,
		"version": settings.VERSION,
		"api_version": "v1",
		"docs": "/v1/docs",
		"openapi": "/v1/openapi.json",
		"health": "/health",
	}


@app.get("/health")
async def health_check() -> dict[str, str]:
	"""Health check endpoint."""
	return {"status": "healthy"}


# Mount API v1
app.mount(API_V1_MOUNT_PATH, v1_app)
