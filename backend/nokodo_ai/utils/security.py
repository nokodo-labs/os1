"""Security-related reusable helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt
from passlib.context import CryptContext


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
	"""Hash a plain-text password using bcrypt."""
	return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
	"""Validate a plain-text password against a hashed value."""
	return _pwd_context.verify(plain_password, hashed_password)


def create_jwt_token(
	subject: str | int,
	*,
	secret_key: str,
	algorithm: str,
	expires_delta: timedelta | None = None,
	additional_claims: Mapping[str, Any] | None = None,
) -> str:
	"""Create a signed JWT for the given subject."""
	expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
	payload: dict[str, Any] = {"sub": str(subject), "exp": expire}
	if additional_claims:
		payload.update(additional_claims)
	return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_jwt_token(
	token: str,
	*,
	secret_key: str,
	algorithms: Sequence[str],
) -> dict[str, Any]:
	"""Decode a JWT token and return its payload."""
	return jwt.decode(token, secret_key, algorithms=list(algorithms))
