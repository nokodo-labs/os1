"""Unit tests for nokodo_ai.utils.security."""

from datetime import timedelta

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
