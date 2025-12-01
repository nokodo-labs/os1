"""api version header middleware for mounted apps."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ._utils import append_header


class APIVersionHeaderMiddleware:
	"""adds an X-API-Version header to responses."""

	__slots__ = ("app", "version")

	def __init__(self, app: ASGIApp, version: str):
		self.app = app
		self.version = version

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		async def send_wrapper(message: Message) -> None:
			if message["type"] == "http.response.start":
				append_header(message, b"x-api-version", self.version)
			await send(message)

		await self.app(scope, receive, send_wrapper)
