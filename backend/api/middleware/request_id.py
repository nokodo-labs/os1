"""request id middleware."""

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.core.logging import request_id_ctx

from ._utils import append_header, get_header


class RequestIDMiddleware:
	"""assigns a request id to every incoming http request."""

	__slots__ = ("app",)

	def __init__(self, app: ASGIApp):
		self.app = app

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		request_id = get_header(scope, b"x-request-id") or str(uuid.uuid4())
		token = request_id_ctx.set(request_id)

		async def send_wrapper(message: Message) -> None:
			if message["type"] == "http.response.start":
				append_header(message, b"x-request-id", request_id)
			await send(message)

		try:
			await self.app(scope, receive, send_wrapper)
		finally:
			request_id_ctx.reset(token)
