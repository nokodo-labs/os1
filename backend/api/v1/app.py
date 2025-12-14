"""API v1 application."""

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from api.core.exceptions import (
	http_exception_handler,
	unhandled_exception_handler,
	validation_exception_handler,
)
from api.core.openapi import DEFAULT_RESPONSES
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

v1_app.add_exception_handler(RequestValidationError, validation_exception_handler)
v1_app.add_exception_handler(HTTPException, http_exception_handler)
v1_app.add_exception_handler(Exception, unhandled_exception_handler)

v1_app.include_router(api_router, responses=DEFAULT_RESPONSES)
v1_app.add_middleware(APIVersionHeaderMiddleware, version="v1")
