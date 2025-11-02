"""Main FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import settings
from api.core.database import init_db
from api.v1.router import api_router


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
	openapi_url=f"{settings.V1_PREFIX}/openapi.json",
	docs_url=f"{settings.V1_PREFIX}/docs",
	redoc_url=f"{settings.V1_PREFIX}/redoc",
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
		"docs": f"{settings.V1_PREFIX}/docs",
		"openapi": f"{settings.V1_PREFIX}/openapi.json",
		"health": "/health",
	}


@app.get("/health")
async def health_check() -> dict[str, str]:
	"""Health check endpoint."""
	return {"status": "healthy"}


# Include API router
app.include_router(api_router, prefix=settings.V1_PREFIX)
