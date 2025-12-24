from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from nokodo_ai.utils import typeid
from nokodo_ai.utils.typeid import TypeID


class _Model(BaseModel):
	id: TypeID


def test_typeid_validates_and_is_str() -> None:
	tid = TypeID(typeid.new_typeid("user"))
	m = _Model(id=tid)
	assert isinstance(m.id, str)
	assert m.id == tid


def test_typeid_rejects_invalid_value() -> None:
	with pytest.raises(ValidationError):
		_Model(id=TypeID("not-a-typeid"))


def test_typeid_json_schema_has_pattern_and_examples() -> None:
	schema = _Model.model_json_schema()
	props = schema.get("properties", {})
	id_schema = props.get("id", {})

	assert "pattern" in id_schema
	assert "examples" in id_schema
	assert id_schema.get("maxLength") == typeid.typeid_max_length()
