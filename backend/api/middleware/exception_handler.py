"""exception handling middleware."""

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from api.core.logging import get_logger, request_id_ctx


logger = get_logger(__name__)


class ExceptionHandlingMiddleware:
	"""normalize uncaught exceptions into json responses."""

	__slots__ = ("app",)

	def __init__(self, app: ASGIApp):
		self.app = app

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		try:
			await self.app(scope, receive, send)
		except HTTPException:
			raise
		except Exception:  # pragma: no cover - defensive logging
			logger.exception(
				"unhandled exception during request",
				extra={
					"path": scope.get("path", "unknown"),
					"method": scope.get("method", "UNKNOWN"),
				},
			)
			payload: dict[str, str] = {"detail": "Internal server error"}
			request_id = request_id_ctx.get()
			if request_id:
				payload["request_id"] = request_id
			response = JSONResponse(payload, status_code=500)
			await response(scope, receive, send)
