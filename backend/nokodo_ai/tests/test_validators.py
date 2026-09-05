"""tests for validation utilities."""

import pytest

from nokodo_ai.utils.validators import validate_single_grapheme


class TestValidateSingleGrapheme:
	@pytest.mark.parametrize(
		"value",
		[
			"a",
			"é",
			"🔐",
			"🖥️",  # emoji + variation selector
			"🇮🇹",  # regional indicator pair (flag)
			"👍🏽",  # skin tone modifier
			"👨‍👩‍👧‍👦",  # ZWJ family sequence
		],
	)
	def test_accepts_single_grapheme(self, value: str) -> None:
		assert validate_single_grapheme(value) == value

	@pytest.mark.parametrize("value", ["", "ab", "🔐🔐", "a️b", " 🔐"])
	def test_rejects_non_single_grapheme(self, value: str) -> None:
		with pytest.raises(ValueError, match="exactly one character"):
			validate_single_grapheme(value)
