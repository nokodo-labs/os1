"""tests for typeid utilities.

these tests validate our implementation against the typeid v0.3.0 spec rules.
"""

from __future__ import annotations

import pytest

from nokodo_ai.utils import typeid


def test_new_typeid_with_prefix_is_valid() -> None:
	tid = typeid.new_typeid("user")
	assert tid.startswith("user_")
	assert tid == tid.lower()
	assert typeid.is_typeid(tid)
	assert typeid.is_typeid(tid, prefix="user")


def test_new_typeid_with_empty_prefix_has_no_separator() -> None:
	tid = typeid.new_typeid("")
	assert "_" not in tid
	assert typeid.is_typeid(tid)


def test_prefix_validation_matches_spec() -> None:
	# valid prefixes
	assert typeid.is_typeid(typeid.new_typeid("a"), prefix="a")
	assert typeid.is_typeid(typeid.new_typeid("my__type"), prefix="my__type")
	assert typeid.is_typeid(typeid.new_typeid("my_type"), prefix="my_type")

	# invalid prefixes
	with pytest.raises(ValueError):
		typeid.new_typeid("PREFIX")
	with pytest.raises(ValueError):
		typeid.new_typeid("12345")
	with pytest.raises(ValueError):
		typeid.new_typeid("_prefix")
	with pytest.raises(ValueError):
		typeid.new_typeid("prefix_")
	with pytest.raises(ValueError):
		typeid.new_typeid("pre-fix")
	with pytest.raises(ValueError):
		typeid.new_typeid("pre.fix")


def test_suffix_validation_is_strict_and_overflow_checked() -> None:
	assert not typeid.is_typeid("prefix_0123456789ABCDEFGHJKMNPQRS")
	assert not typeid.is_typeid("prefix_8zzzzzzzzzzzzzzzzzzzzzzzzz")
	assert not typeid.is_typeid("prefix_01h5fskfsk4fpeqwnsyz5hj55")


def test_generated_uuid_is_uuidv7() -> None:
	tid = typeid.new_typeid("user")
	uuid_bytes = typeid.decode_uuid_bytes_from_typeid(tid)

	# version is high nibble of byte 6
	assert (uuid_bytes[6] >> 4) == 0x7
	# variant is top two bits of byte 8
	assert (uuid_bytes[8] >> 6) == 0b10


def test_uuid7_timestamp_range_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(typeid.time, "time_ns", lambda: -1)
	with pytest.raises(ValueError, match="timestamp out of range"):
		typeid.new_typeid("user")

	# 48-bit max ms: 0xFFFFFFFFFFFF
	too_large_ms = 0x1_0000_0000_0000
	monkeypatch.setattr(typeid.time, "time_ns", lambda: too_large_ms * 1_000_000)
	with pytest.raises(ValueError, match="timestamp out of range"):
		typeid.new_typeid("user")


def test_encode_uuid_suffix_requires_16_bytes() -> None:
	with pytest.raises(ValueError, match="uuid must be 16 bytes"):
		typeid._encode_base32_uuid_suffix(b"")

	encoded = typeid._encode_base32_uuid_suffix(b"\x00" * 16)
	assert len(encoded) == typeid.TYPEID_SUFFIX_LENGTH
	assert encoded.startswith("0")


def test_decode_suffix_rejects_invalid_inputs() -> None:
	with pytest.raises(ValueError, match="invalid typeid suffix length"):
		typeid._decode_base32_uuid_suffix("0" * 25)

	with pytest.raises(ValueError, match="invalid typeid suffix"):
		typeid._decode_base32_uuid_suffix("0" * 25 + "i")

	with pytest.raises(ValueError, match="overflow"):
		typeid._decode_base32_uuid_suffix("8" + ("0" * 25))


def test_decode_uuid_bytes_accepts_suffix_only_typeid() -> None:
	tid = typeid.new_typeid("")
	uuid_bytes = typeid.decode_uuid_bytes_from_typeid(tid)
	assert isinstance(uuid_bytes, bytes)
	assert len(uuid_bytes) == 16


def test_decode_uuid_bytes_rejects_invalid_typeid() -> None:
	with pytest.raises(ValueError, match="invalid typeid"):
		typeid.decode_uuid_bytes_from_typeid("not-a-typeid")


def test_new_typeid_rejects_too_long_prefix() -> None:
	with pytest.raises(ValueError, match="<= 63"):
		typeid.new_typeid("a" * 64)


def test_is_typeid_rejects_non_string_and_empty_prefix_part() -> None:
	assert not typeid.is_typeid(123)  # type: ignore[arg-type]
	assert not typeid.is_typeid("")

	suffix = typeid.new_typeid("")
	assert not typeid.is_typeid(f"_{suffix}")
	assert not typeid.is_typeid(f"user_{suffix}", prefix="org")
	assert not typeid.is_typeid(suffix, prefix="user")

	too_long_prefix = "a" * 64
	assert not typeid.is_typeid(f"{too_long_prefix}_{suffix}")
	assert not typeid.is_typeid(f"a__{suffix}")

	assert not typeid.is_typeid("user_" + ("0" * 25))
	assert not typeid.is_typeid("user_" + ("0" * 25) + "i")


def test_assert_typeid_has_clear_error_messages() -> None:
	with pytest.raises(ValueError, match="^invalid typeid$"):
		typeid.assert_typeid("not-a-typeid")

	tid = typeid.new_typeid("org")
	with pytest.raises(ValueError, match=r"expected prefix 'user'"):
		typeid.assert_typeid(tid, prefix="user")

	valid = typeid.new_typeid("user")
	assert typeid.assert_typeid(valid, prefix="user") == valid
