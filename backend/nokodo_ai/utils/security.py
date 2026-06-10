"""Security-related reusable helpers."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from joserfc import jwt
from joserfc.jwk import OctKey
from joserfc.jwt import JWTClaimsRegistry


_PASSWORD_HASHER = PasswordHasher(
	time_cost=3,
	memory_cost=2**16,
	parallelism=2,
	hash_len=32,
	salt_len=16,
)


def hash_password(password: str) -> str:
	"""Hash a plain-text password using Argon2id."""
	return _PASSWORD_HASHER.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
	"""Validate a plain-text password against an Argon2id hash."""
	try:
		_PASSWORD_HASHER.verify(hashed_password, plain_password)
	except VerifyMismatchError, InvalidHash:
		return False
	return True


def create_jwt_token(
	subject: str | int,
	secret_key: str,
	algorithm: str,
	expires_delta: timedelta | None = None,
	additional_claims: Mapping[str, Any] | None = None,
) -> str:
	"""Create a signed JWT for the given subject."""
	expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
	payload: dict[str, Any] = {"sub": str(subject), "exp": int(expire.timestamp())}
	if additional_claims:
		payload.update(additional_claims)
	headers = {"alg": algorithm, "typ": "JWT"}
	key = OctKey.import_key(secret_key)
	return jwt.encode(headers, payload, key, algorithms=[algorithm])


def decode_jwt_token(
	token: str,
	secret_key: str,
	algorithms: Sequence[str],
) -> dict[str, Any]:
	"""Decode a JWT token and return its payload."""
	key = OctKey.import_key(secret_key)
	token_obj = jwt.decode(token, key, algorithms=list(algorithms))
	registry = JWTClaimsRegistry(
		now=int(datetime.now(UTC).timestamp()),
		exp={"essential": True},
	)
	registry.validate(token_obj.claims)
	return token_obj.claims


def get_fernet_key(secret_key: str) -> bytes:
	"""Derive a 32-byte key from a secret string."""
	key = hashlib.sha256(secret_key.encode()).digest()
	return base64.urlsafe_b64encode(key)


def encrypt_string(plain_text: str, secret_key: str) -> str:
	"""Encrypt a string."""
	f = Fernet(get_fernet_key(secret_key))
	return f.encrypt(plain_text.encode()).decode()


def decrypt_string(cipher_text: str, secret_key: str) -> str:
	"""Decrypt a string."""
	f = Fernet(get_fernet_key(secret_key))
	return f.decrypt(cipher_text.encode()).decode()


def decrypt_string_with_fallback(
	cipher_text: str,
	secret_key: str,
	previous_keys: Sequence[str] = (),
	strict: bool = False,
) -> tuple[str, bool]:
	"""Decrypt trying the current key first, then previous keys.

	Returns (plaintext, needs_reencrypt) where needs_reencrypt is True
	when an old key was used and the caller should re-encrypt with the current key.

	Pass strict=True to ignore previous_keys entirely and require the current key.
	"""
	try:
		return decrypt_string(cipher_text, secret_key), False
	except InvalidToken:
		pass
	if not strict:
		for old_key in previous_keys:
			try:
				return decrypt_string(cipher_text, old_key), True
			except InvalidToken:
				continue
	raise InvalidToken()
