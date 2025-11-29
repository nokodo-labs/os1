"""Unit tests for nokodo_ai.utils.security."""

from datetime import timedelta

import pytest
from authlib.jose import JoseError

from nokodo_ai.utils.security import (
	create_jwt_token,
	decode_jwt_token,
	hash_password,
	verify_password,
)


def test_hash_and_verify_password_roundtrip() -> None:
	"""Hashing should be non-reversible yet verifiable."""
	plain = "super-secret-password"
	hashed = hash_password(plain)
	assert hashed != plain
	assert hashed.startswith("$argon2id$")
	assert verify_password(plain, hashed)
	assert verify_password("wrong-password", hashed) is False


def test_jwt_encode_decode_with_additional_claims() -> None:
	"""Generated tokens should round-trip and expose custom claims."""
	secret = "unit-test-secret"
	token = create_jwt_token(
		subject=42,
		secret_key=secret,
		algorithm="HS256",
		expires_delta=timedelta(minutes=5),
		additional_claims={"scope": "test", "roles": ["reader"]},
	)
	payload = decode_jwt_token(token, secret_key=secret, algorithms=["HS256"])
	assert payload["sub"] == "42"
	assert payload["scope"] == "test"
	assert payload["roles"] == ["reader"]
	assert "exp" in payload
	assert payload["exp"] > 0


def test_jwt_decode_invalid_algorithm() -> None:
	"""Decoding with an unexpected algorithm should raise an error."""
	secret = "unit-test-secret"
	# Create a token with HS256
	token = create_jwt_token(
		subject=1,
		secret_key=secret,
		algorithm="HS256",
	)

	# Try to decode allowing only HS512
	with pytest.raises(JoseError, match="unexpected_alg"):
		decode_jwt_token(token, secret_key=secret, algorithms=["HS512"])
