"""Unit tests for nokodo_ai.utils.security."""

from datetime import timedelta

import pytest
from cryptography.fernet import InvalidToken
from joserfc.errors import JoseError

from nokodo_ai.utils.security import (
	create_jwt_token,
	decode_jwt_token,
	decrypt_string,
	decrypt_string_with_fallback,
	encrypt_string,
	get_fernet_key,
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
	with pytest.raises(JoseError):
		decode_jwt_token(token, secret_key=secret, algorithms=["HS512"])


def test_encrypt_and_decrypt_string_roundtrip() -> None:
	"""Strings should round-trip through Fernet encryption."""
	secret = "unit-test-fernet"
	plain = "sensitive-data"
	cipher = encrypt_string(plain, secret)
	assert cipher != plain
	assert decrypt_string(cipher, secret) == plain


def test_get_fernet_key_is_stable_and_valid_length() -> None:
	"""Derived keys should be deterministic and URL-safe length for Fernet."""
	key1 = get_fernet_key("shared-secret")
	key2 = get_fernet_key("shared-secret")
	assert key1 == key2
	assert len(key1) == 44
	allowed = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")
	assert set(key1) <= allowed
	assert key1.endswith(b"=")


def test_decrypt_with_fallback_current_key() -> None:
	"""fallback decrypt should use the current key when it matches."""
	plain = "my-api-key"
	current = "current-secret"
	cipher = encrypt_string(plain, current)
	result, needs_reencrypt = decrypt_string_with_fallback(cipher, current)
	assert result == plain
	assert needs_reencrypt is False


def test_decrypt_with_fallback_old_key() -> None:
	"""fallback decrypt should find the value via a previous key."""
	plain = "my-api-key"
	old_key = "old-secret"
	new_key = "new-secret"
	cipher = encrypt_string(plain, old_key)
	result, needs_reencrypt = decrypt_string_with_fallback(
		cipher, new_key, previous_keys=[old_key]
	)
	assert result == plain
	assert needs_reencrypt is True


def test_decrypt_with_fallback_no_matching_key() -> None:
	"""fallback decrypt should raise InvalidToken when no key works."""
	cipher = encrypt_string("secret", "original-key")
	with pytest.raises(InvalidToken):
		decrypt_string_with_fallback(cipher, "wrong-key", ["also-wrong"])


def test_decrypt_with_fallback_multiple_old_keys() -> None:
	"""fallback should try old keys in order."""
	plain = "rotated-value"
	oldest = "key-v1"
	middle = "key-v2"
	current = "key-v3"
	cipher = encrypt_string(plain, oldest)
	result, needs_reencrypt = decrypt_string_with_fallback(
		cipher, current, [middle, oldest]
	)
	assert result == plain
	assert needs_reencrypt is True


def test_decrypt_with_fallback_strict_ignores_previous_keys() -> None:
	"""strict=True should not try previous keys even if they would succeed."""
	plain = "sensitive"
	old_key = "old-secret"
	new_key = "new-secret"
	cipher = encrypt_string(plain, old_key)
	with pytest.raises(InvalidToken):
		decrypt_string_with_fallback(cipher, new_key, [old_key], strict=True)
