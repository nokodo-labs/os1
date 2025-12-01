"""exception handlers for fastapi application."""

from typing import Any, cast

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.core.logging import get_logger, request_id_ctx


logger = get_logger(__name__)


def _build_payload(detail: Any) -> dict[str, Any]:
	"""construct error response payload with optional request id."""
	payload: dict[str, Any] = {"detail": detail}
	request_id = request_id_ctx.get()
	if request_id:
		payload["request_id"] = request_id
	return payload


async def validation_exception_handler(
	request: Request, exc: Exception
) -> JSONResponse:
	"""handle pydantic validation errors."""
	exc = cast(RequestValidationError, exc)
	return JSONResponse(status_code=422, content=_build_payload(exc.errors()))


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
	"""catch-all for unhandled exceptions."""
	if isinstance(exc, HTTPException):  # preserve native FastAPI handling
		raise exc
	logger.exception(
		"unhandled exception during request",
		extra={"path": request.url.path, "method": request.method},
	)
	return JSONResponse(
		status_code=500, content=_build_payload("Internal server error")
	)
