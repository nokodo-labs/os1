from __future__ import annotations

from typing import get_args

from api.schemas.message import AttachmentRefType
from api.v1.service.chat.filters.attachments import (
	_RESOLUTION_TOOL,
	_ref_is_resolvable,
)


def test_resolution_tool_covers_all_ref_types() -> None:
	"""every attachment ref type maps to a resolution tool, so none is silently unresolvable."""
	for ref_type in get_args(AttachmentRefType):
		assert ref_type in _RESOLUTION_TOOL


def test_ref_is_resolvable_requires_the_tool() -> None:
	assert _ref_is_resolvable("file", {"file_get"}) is True
	assert _ref_is_resolvable("file", {"note_get"}) is False
	assert _ref_is_resolvable("file", set()) is False


def test_ref_is_resolvable_maps_each_type_to_its_tool() -> None:
	assert _ref_is_resolvable("note", {"note_get"}) is True
	assert _ref_is_resolvable("thread", {"chat_get"}) is True
	assert _ref_is_resolvable("calendar_event", {"calendar_event_get"}) is True


def test_ref_is_resolvable_unknown_type_is_never_resolvable() -> None:
	assert _ref_is_resolvable("unknown", {"file_get", "note_get"}) is False
