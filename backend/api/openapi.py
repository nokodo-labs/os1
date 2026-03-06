"""OpenAPI utilities and shared response metadata."""

from __future__ import annotations

from api.schemas.errors import ProblemDetails, ValidationProblemDetails


# TODO: move this constant somewhere else. not sure if constants.py is the best
# since it requires imports from /schemas.
DEFAULT_RESPONSES: dict[int | str, dict[str, object]] = {
	400: {
		"description": "bad request",
		"model": ProblemDetails,
	},
	401: {
		"description": "unauthorized",
		"model": ProblemDetails,
	},
	403: {
		"description": "forbidden",
		"model": ProblemDetails,
	},
	404: {
		"description": "not found",
		"model": ProblemDetails,
	},
	409: {
		"description": "conflict",
		"model": ProblemDetails,
	},
	422: {
		"description": "validation error",
		"model": ValidationProblemDetails,
	},
	429: {
		"description": "too many requests",
		"model": ProblemDetails,
	},
	500: {
		"description": "internal server error",
		"model": ProblemDetails,
	},
}
