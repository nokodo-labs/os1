"""exception handlers for fastapi application."""

from __future__ import annotations

from http import HTTPStatus

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.core.logging import get_logger, request_id_ctx
from api.schemas.errors import ProblemDetails, ValidationIssue, ValidationProblemDetails


logger = get_logger(__name__)


def _get_request_id() -> str | None:
	request_id = request_id_ctx.get()
	return request_id or None


def _status_title(status_code: int) -> str:
	# avoid auto-capitalization in user-facing text
	try:
		return HTTPStatus(status_code).phrase.lower()
	except ValueError:
		return "error"


def _coerce_detail(detail: object) -> tuple[str | None, object | None]:
	if detail is None:
		return None, None
	if isinstance(detail, str):
		return detail, None
	# keep structured payloads in an extension field
	return None, detail


def _parse_validation_issues(exc: RequestValidationError) -> list[ValidationIssue]:
	issues: list[ValidationIssue] = []
	for err in exc.errors():
		loc = [part for part in err.get("loc", [])]
		issues.append(
			ValidationIssue(
				type=str(err.get("type", "validation_error")),
				loc=loc,
				message=str(err.get("msg", "invalid request")),
				input=err.get("input"),
				context=err.get("ctx"),
			)
		)
	return issues


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
	"""handle http exceptions with a consistent envelope."""
	if not isinstance(exc, HTTPException):
		raise exc
	detail, data = _coerce_detail(exc.detail)
	if detail is not None and detail.lower() == _status_title(exc.status_code):
		detail = None
	payload = ProblemDetails(
		type="about:blank",
		title=_status_title(exc.status_code),
		status=exc.status_code,
		detail=detail,
		instance=request.url.path,
		request_id=_get_request_id(),
		data=data,
	)
	return JSONResponse(
		status_code=exc.status_code,
		content=payload.model_dump(exclude_none=True),
		media_type="application/problem+json",
	)


async def validation_exception_handler(
	request: Request, exc: Exception
) -> JSONResponse:
	"""handle pydantic validation errors."""
	if not isinstance(exc, RequestValidationError):
		raise exc
	# RequestValidationError may include arbitrary input, so avoid putting it into
	# `detail` and use structured errors instead.
	payload = ValidationProblemDetails(
		detail="request validation failed",
		instance=request.url.path,
		request_id=_get_request_id(),
		errors=_parse_validation_issues(exc),
	)
	return JSONResponse(
		status_code=422,
		content=payload.model_dump(exclude_none=True),
		media_type="application/problem+json",
	)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
	"""catch-all for unhandled exceptions."""
	if isinstance(exc, HTTPException):
		raise exc
	logger.exception(
		"unhandled exception during request",
		extra={"path": request.url.path, "method": request.method},
	)
	payload = ProblemDetails(
		type="urn:nokodo:internal-error",
		title=_status_title(500),
		status=500,
		detail="internal server error",
		instance=request.url.path,
		request_id=_get_request_id(),
	)
	return JSONResponse(
		status_code=500,
		content=payload.model_dump(exclude_none=True),
		media_type="application/problem+json",
	)
