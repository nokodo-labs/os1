"""Coverage-focused tests for api.core.exceptions helpers."""

from __future__ import annotations

from fastapi.exceptions import RequestValidationError

from api.core.exceptions import _make_json_safe, _parse_validation_issues, _status_title


def test_make_json_safe_handles_nested_types() -> None:
	value = {
		"a": ValueError("nope"),
		"b": [1, 2, {"x": object()}],
		3: (True, None),
	}
	safe = _make_json_safe(value)

	assert isinstance(safe, dict)
	assert safe["a"] == "nope"
	assert safe["b"][2]["x"] == str(value["b"][2]["x"])
	assert safe["3"][0] is True
	assert safe["3"][1] is None


def test_status_title_handles_unknown_status_codes() -> None:
	assert _status_title(418) == "i'm a teapot"
	assert _status_title(999) == "error"


def test_parse_validation_issues_ignores_non_dict_ctx() -> None:
	exc = RequestValidationError(
		errors=[
			{
				"loc": ("body", "x"),
				"msg": "bad",
				"type": "value_error",
				"ctx": "not-a-dict",
			}
		]
	)
	issues = _parse_validation_issues(exc)
	assert len(issues) == 1
	assert issues[0].context is None


def test_parse_validation_issues_sanitizes_dict_ctx() -> None:
	exc = RequestValidationError(
		errors=[
			{
				"loc": ("body", "x"),
				"msg": "bad",
				"type": "value_error",
				"ctx": {"err": ValueError("boom"), "extra": [object()]},
			}
		]
	)
	issues = _parse_validation_issues(exc)
	assert len(issues) == 1
	assert issues[0].context is not None
	assert issues[0].context["err"] == "boom"
