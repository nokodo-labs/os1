"""API v1 application."""

from fastapi import FastAPI

from api.middleware import APIVersionHeaderMiddleware
from api.v1.router import api_router


v1_app = FastAPI(
	title="nokodo AI API v1",
	version="1.0.0",
	description="API v1 documentation",
	docs_url="/docs",
	redoc_url="/redoc",
	openapi_url="/openapi.json",
)

v1_app.include_router(api_router)
v1_app.add_middleware(APIVersionHeaderMiddleware, version="v1")
