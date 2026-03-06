"""internal helpers for middleware components."""

from starlette.types import Message, Scope


def get_header(scope: Scope, key: bytes) -> str | None:
	"""return the first header value for the given key."""
	headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
	for header_key, header_value in headers:
		if header_key == key:
			return header_value.decode("latin-1")
	return None


def get_client_ip(scope: Scope) -> str:
	"""derive client ip from forwarded headers or socket info."""
	forwarded = get_header(scope, b"x-forwarded-for")
	if forwarded:
		return forwarded.split(",", 1)[0].strip()
	client = scope.get("client")
	return client[0] if client else "unknown"


def append_header(message: Message, key: bytes, value: str) -> None:
	"""append a header to the asgi message in-place."""
	headers = list(message.get("headers", []))
	headers.append((key, value.encode("latin-1")))
	message["headers"] = headers
