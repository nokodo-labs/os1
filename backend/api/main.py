"""Main FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.constants import API_V1_MOUNT_PATH
from api.core.config import settings
from api.core.database import init_db
from api.v1.app import v1_app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
	"""Application lifespan events."""
	# Startup: skip DB init during tests
	from api.core.config import settings

	if not settings.TESTING:
		await init_db()
	yield
	# Shutdown
	# Add cleanup logic here if needed


app = FastAPI(
	title=settings.PROJECT_NAME,
	version=settings.VERSION,
	lifespan=lifespan,
)


# Set up CORS
app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.CORS_ORIGINS,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


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
