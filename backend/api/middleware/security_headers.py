"""security headers middleware."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.boot_settings import boot_settings

from ._utils import append_header


DEFAULT_HEADERS = {
	b"x-content-type-options": "nosniff",
	b"referrer-policy": "strict-origin-when-cross-origin",
	b"x-frame-options": "DENY",
	b"permissions-policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware:
	"""adds opinionated security headers to responses."""

	__slots__ = ("app",)

	def __init__(self, app: ASGIApp):
		self.app = app

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		async def send_wrapper(message: Message) -> None:
			if message["type"] == "http.response.start":
				for header, value in DEFAULT_HEADERS.items():
					append_header(message, header, value)
				if boot_settings.ENV != "dev":
					append_header(
						message,
						b"strict-transport-security",
						"max-age=63072000; includeSubDomains; preload",
					)
			await send(message)

		await self.app(scope, receive, send_wrapper)
