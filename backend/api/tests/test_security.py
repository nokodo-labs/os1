"""Tests for security utilities."""

from datetime import timedelta

import pytest
from authlib.jose import JoseError

from nokodo_ai.utils.security import (
	create_jwt_token,
	decode_jwt_token,
	decrypt_string,
	encrypt_string,
	get_fernet_key,
	hash_password,
	verify_password,
)


def test_encryption_decryption() -> None:
	"""Test that encryption and decryption work correctly."""
	secret_key = "test-secret-key"
	plain_text = "hello world"

	encrypted = encrypt_string(plain_text, secret_key)
	assert encrypted != plain_text

	decrypted = decrypt_string(encrypted, secret_key)
	assert decrypted == plain_text


def test_get_fernet_key() -> None:
	"""Test key derivation."""
	secret_key = "test-secret-key"
	key1 = get_fernet_key(secret_key)
	key2 = get_fernet_key(secret_key)

	assert len(key1) == 44  # Base64 encoded 32 bytes
	assert key1 == key2

	key3 = get_fernet_key("different-key")
	assert key1 != key3


def test_password_hashing() -> None:
	"""Test password hashing and verification."""
	password = "secure-password"
	hashed = hash_password(password)

	assert hashed != password
	assert verify_password(password, hashed)
	assert not verify_password("wrong-password", hashed)
	assert not verify_password(password, "invalid-hash")


def test_jwt_token_creation_and_decoding() -> None:
	"""Test JWT token creation and decoding."""
	secret_key = "jwt-secret-key"
	algorithm = "HS256"
	subject = "user-123"
	additional_claims = {"role": "admin"}

	token = create_jwt_token(
		subject,
		secret_key=secret_key,
		algorithm=algorithm,
		additional_claims=additional_claims,
	)

	decoded = decode_jwt_token(
		token,
		secret_key=secret_key,
		algorithms=[algorithm],
	)

	assert decoded["sub"] == subject
	assert decoded["role"] == "admin"
	assert "exp" in decoded


def test_jwt_token_expiration() -> None:
	"""Test JWT token expiration."""
	secret_key = "jwt-secret-key"
	algorithm = "HS256"
	subject = "user-123"

	# Create a token that expires immediately
	token = create_jwt_token(
		subject,
		secret_key=secret_key,
		algorithm=algorithm,
		expires_delta=timedelta(seconds=-1),
	)

	with pytest.raises(JoseError):
		decode_jwt_token(
			token,
			secret_key=secret_key,
			algorithms=[algorithm],
		)


def test_jwt_token_invalid_algorithm() -> None:
	"""Test JWT token with invalid algorithm."""
	secret_key = "jwt-secret-key"
	algorithm = "HS256"
	subject = "user-123"

	token = create_jwt_token(
		subject,
		secret_key=secret_key,
		algorithm=algorithm,
	)

	# Try to decode with a different algorithm allowed
	with pytest.raises(JoseError):
		decode_jwt_token(
			token,
			secret_key=secret_key,
			algorithms=["RS256"],
		)
