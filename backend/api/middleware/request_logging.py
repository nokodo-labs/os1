"""request logging middleware with latency headers."""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.logging import get_logger

from ._utils import append_header, get_client_ip


logger = get_logger(__name__)


class RequestLoggingMiddleware:
	"""logs request lifecycle and emits timing headers."""

	__slots__ = ("app",)

	def __init__(self, app: ASGIApp):
		self.app = app

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		start_time = time.perf_counter()
		method = scope.get("method", "UNKNOWN")
		path = scope.get("path", "unknown")
		client_ip = get_client_ip(scope)
		status_code = 500

		async def send_wrapper(message: Message) -> None:
			nonlocal status_code
			if message["type"] == "http.response.start":
				duration_ms = (time.perf_counter() - start_time) * 1000
				status_code = message.get("status", 500)
				append_header(message, b"x-process-time", f"{duration_ms:.2f}ms")
				append_header(message, b"server-timing", f"app;dur={duration_ms:.2f}")
			await send(message)

		try:
			await self.app(scope, receive, send_wrapper)
			self._log(method, path, status_code, start_time, client_ip)
		except Exception:
			self._log(method, path, 500, start_time, client_ip, error=True)
			raise

	def _log(
		self,
		method: str,
		path: str,
		status_code: int,
		start_time: float,
		client_ip: str,
		error: bool = False,
	) -> None:
		duration = (time.perf_counter() - start_time) * 1000
		log_func = logger.info
		if status_code >= 500 or error:
			log_func = logger.error
		elif status_code >= 400:
			log_func = logger.warning

		log_func(
			f"{method} {path} {status_code} - {duration:.2f}ms",
			extra={
				"method": method,
				"path": path,
				"status": status_code,
				"duration_ms": round(duration, 2),
				"ip": client_ip,
			},
		)
