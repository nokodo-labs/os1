from __future__ import annotations

import re
import secrets
import time
from typing import Final


TYPEID_SEPARATOR: Final[str] = "_"
TYPEID_SUFFIX_LENGTH: Final[int] = 26
TYPEID_MAX_PREFIX_LENGTH: Final[int] = 63
TYPEID_MAX_LENGTH: Final[int] = 90

_BASE32_ALPHABET: Final[str] = "0123456789abcdefghjkmnpqrstvwxyz"

_BASE32_DECODE_TABLE: Final[dict[str, int]] = {
	char: index for index, char in enumerate(_BASE32_ALPHABET)
}

# spec v0.3.0: ^([a-z]([a-z_]{0,61}[a-z])?)?$
_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^([a-z]([a-z_]{0,61}[a-z])?)?$")
_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
	r"^[0123456789abcdefghjkmnpqrstvwxyz]{26}$"
)


def typeid_max_length() -> int:
	return TYPEID_MAX_LENGTH


def _uuid7_bytes() -> bytes:
	# uuidv7 per rfc9562 layout:
	# - 48-bit unix epoch ms
	# - version 7
	# - 12 bits rand_a
	# - variant 10
	# - 62 bits rand_b
	ms = time.time_ns() // 1_000_000
	if ms < 0 or ms > 0xFFFFFFFFFFFF:
		raise ValueError("timestamp out of range for uuidv7")

	rand_a = secrets.randbits(12)
	rand_b = secrets.randbits(62)

	uuid_int = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
	return uuid_int.to_bytes(16, byteorder="big", signed=False)


def _encode_base32_uuid_suffix(uuid_bytes: bytes) -> str:
	if len(uuid_bytes) != 16:
		raise ValueError("uuid must be 16 bytes")

	uuid_int = int.from_bytes(uuid_bytes, byteorder="big", signed=False)
	# base32 encoding per spec v0.3.0:
	# treat uuid as 128 bits, prepend two zero bits on the left => 130 bits.
	# then emit 26 groups of 5 bits from most-significant to least.
	chars: list[str] = []
	for group_index in range(TYPEID_SUFFIX_LENGTH):
		shift = 125 - (group_index * 5)
		value = (uuid_int >> shift) & 0x1F
		chars.append(_BASE32_ALPHABET[value])
	return "".join(chars)


def decode_uuid_bytes_from_typeid(value: str) -> bytes:
	"""Decode a TypeID string into raw UUID bytes.

	This accepts either:
	- <prefix>_<suffix>
	- <suffix> (empty prefix)

	Raises ValueError if the input is not a valid TypeID.
	"""
	if not is_typeid(value):
		raise ValueError("invalid typeid")

	if TYPEID_SEPARATOR not in value:
		suffix = value
	else:
		suffix = value[value.rfind(TYPEID_SEPARATOR) + 1 :]
	return _decode_base32_uuid_suffix(suffix)


def _decode_base32_uuid_suffix(suffix: str) -> bytes:
	if len(suffix) != TYPEID_SUFFIX_LENGTH:
		raise ValueError("invalid typeid suffix length")
	if not _SUFFIX_RE.fullmatch(suffix):
		raise ValueError("invalid typeid suffix")
	if suffix[0] not in "01234567":
		raise ValueError("invalid typeid suffix: overflow")

	value_130 = 0
	for char in suffix:
		value_130 = (value_130 << 5) | _BASE32_DECODE_TABLE[char]

	# drop the leading two zero bits
	uuid_int = value_130 & ((1 << 128) - 1)
	return uuid_int.to_bytes(16, byteorder="big", signed=False)


def new_typeid(prefix: str) -> str:
	if len(prefix) > TYPEID_MAX_PREFIX_LENGTH:
		raise ValueError("invalid typeid prefix: must be <= 63 characters")
	if not _PREFIX_RE.fullmatch(prefix):
		raise ValueError(
			"invalid typeid prefix: must match ^([a-z]([a-z_]{0,61}[a-z])?)?$"
		)

	suffix = _encode_base32_uuid_suffix(_uuid7_bytes())
	if prefix == "":
		return suffix
	return f"{prefix}{TYPEID_SEPARATOR}{suffix}"


def is_typeid(value: str, *, prefix: str | None = None) -> bool:
	if not isinstance(value, str):
		return False

	if value == "":
		return False

	if TYPEID_SEPARATOR not in value:
		prefix_part = ""
		suffix_part = value
	else:
		sep_index = value.rfind(TYPEID_SEPARATOR)
		prefix_part = value[:sep_index]
		suffix_part = value[sep_index + 1 :]
		if prefix_part == "":
			return False

	if len(prefix_part) > TYPEID_MAX_PREFIX_LENGTH:
		return False
	if not _PREFIX_RE.fullmatch(prefix_part):
		return False
	if prefix is not None and prefix_part != prefix:
		return False

	if len(suffix_part) != TYPEID_SUFFIX_LENGTH:
		return False
	if not _SUFFIX_RE.fullmatch(suffix_part):
		return False
	# prevent overflow beyond 128 bits
	if suffix_part[0] not in "01234567":
		return False

	return True


def assert_typeid(value: str, *, prefix: str | None = None) -> str:
	if not is_typeid(value, prefix=prefix):
		if prefix is None:
			raise ValueError("invalid typeid")
		raise ValueError(f"invalid typeid: expected prefix '{prefix}'")
	return value
