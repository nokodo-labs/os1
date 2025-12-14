"""OpenAPI utilities and shared response metadata."""

from __future__ import annotations

from api.schemas.errors import ProblemDetails, ValidationProblemDetails


# TODO: move this constant somewhere else. not sure if constants.py is the best
# since it requires imports from /schemas.
DEFAULT_RESPONSES: dict[int | str, dict[str, object]] = {
	400: {
		"description": "bad request",
		"content": {"application/problem+json": {"model": ProblemDetails}},
	},
	401: {
		"description": "unauthorized",
		"content": {"application/problem+json": {"model": ProblemDetails}},
	},
	403: {
		"description": "forbidden",
		"content": {"application/problem+json": {"model": ProblemDetails}},
	},
	404: {
		"description": "not found",
		"content": {"application/problem+json": {"model": ProblemDetails}},
	},
	409: {
		"description": "conflict",
		"content": {"application/problem+json": {"model": ProblemDetails}},
	},
	422: {
		"description": "validation error",
		"content": {"application/problem+json": {"model": ValidationProblemDetails}},
	},
	429: {
		"description": "too many requests",
		"content": {"application/problem+json": {"model": ProblemDetails}},
	},
	500: {
		"description": "internal server error",
		"content": {"application/problem+json": {"model": ProblemDetails}},
	},
}
