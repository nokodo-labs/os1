"""unit tests for the vectorstore service filter builders.

all tests are pure unit tests - no db, no qdrant connection required.
"""

from __future__ import annotations

from api.v1.service.vectorstores import acl_filter, resource_filter
from nokodo_ai.adapters.base.vectorstores import ChunkFilter, FieldMatch, FieldMatchAny


# -- helpers -----------------------------------------------------------------


def field_match_keys(matches: list) -> set[str]:
	"""Return the set of keys from FieldMatch entries in a match list."""
	return {m.key for m in matches if isinstance(m, FieldMatch)}


def match_any_entries(matches: list) -> list[FieldMatchAny]:
	"""Return only FieldMatchAny entries from a match list."""
	return [m for m in matches if isinstance(m, FieldMatchAny)]


# -- resource_filter ---------------------------------------------------------


def test_resource_filter_type_only() -> None:
	f = resource_filter("note")
	assert isinstance(f, ChunkFilter)
	assert len(f.all_of) == 1
	assert isinstance(f.all_of[0], FieldMatch)
	assert f.all_of[0].key == "resource_type"
	assert f.all_of[0].value == "note"
	assert f.any_of == []


def test_resource_filter_with_resource_id() -> None:
	f = resource_filter("note", resource_id="abc-123")
	assert len(f.all_of) == 2
	keys = field_match_keys(f.all_of)
	assert "resource_type" in keys
	assert "resource_id" in keys
	rid = next(
		m for m in f.all_of if isinstance(m, FieldMatch) and m.key == "resource_id"
	)
	assert rid.value == "abc-123"


def test_resource_filter_with_owner_id() -> None:
	f = resource_filter("thread", owner_id="user-99")
	assert len(f.all_of) == 2
	keys = field_match_keys(f.all_of)
	assert "resource_type" in keys
	assert "owner_id" in keys


def test_resource_filter_with_resource_id_and_owner_id() -> None:
	f = resource_filter("reminder", resource_id="r1", owner_id="u1")
	assert len(f.all_of) == 3
	assert field_match_keys(f.all_of) == {"resource_type", "resource_id", "owner_id"}


def test_resource_filter_any_of_always_empty() -> None:
	f = resource_filter("memory", resource_id="m1", owner_id="u1")
	assert f.any_of == []


# -- acl_filter - admin path -------------------------------------------------


def test_acl_filter_admin_returns_type_only_filter() -> None:
	f = acl_filter("note", is_admin=True, user_id="admin-user")
	assert isinstance(f, ChunkFilter)
	assert len(f.all_of) == 1
	assert isinstance(f.all_of[0], FieldMatch)
	assert f.all_of[0].key == "resource_type"
	assert f.all_of[0].value == "note"
	# admin sees everything - no any_of restrictions
	assert f.any_of == []


def test_acl_filter_admin_ignores_groups_and_roles() -> None:
	f = acl_filter(
		"thread",
		is_admin=True,
		user_id="u1",
		group_ids=["g1", "g2"],
		role_ids=["r1"],
	)
	assert f.any_of == []


# -- acl_filter - regular user path ------------------------------------------


def test_acl_filter_regular_user_includes_resource_type_in_all_of() -> None:
	f = acl_filter("note", is_admin=False, user_id="u1")
	assert any(
		isinstance(m, FieldMatch) and m.key == "resource_type" and m.value == "note"
		for m in f.all_of
	)


def test_acl_filter_regular_user_any_of_has_owner_and_user_checks() -> None:
	f = acl_filter("note", is_admin=False, user_id="uid-42")
	# must contain owner_id == uid-42 and allowed_user_ids == uid-42
	any_of_by_key = {m.key: m for m in f.any_of if isinstance(m, FieldMatch)}
	assert "owner_id" in any_of_by_key
	assert any_of_by_key["owner_id"].value == "uid-42"
	assert "allowed_user_ids" in any_of_by_key
	assert any_of_by_key["allowed_user_ids"].value == "uid-42"


def test_acl_filter_adds_group_ids_as_match_any() -> None:
	f = acl_filter("note", is_admin=False, user_id="u1", group_ids=["g1", "g2"])
	entries = match_any_entries(f.any_of)
	assert len(entries) == 1
	assert entries[0].key == "allowed_group_ids"
	assert set(entries[0].values) == {"g1", "g2"}


def test_acl_filter_adds_role_ids_as_match_any() -> None:
	f = acl_filter("thread", is_admin=False, user_id="u1", role_ids=["r1", "r2"])
	entries = match_any_entries(f.any_of)
	assert len(entries) == 1
	assert entries[0].key == "allowed_role_ids"
	assert set(entries[0].values) == {"r1", "r2"}


def test_acl_filter_adds_both_group_and_role_ids() -> None:
	f = acl_filter(
		"note",
		is_admin=False,
		user_id="u1",
		group_ids=["g1"],
		role_ids=["r1"],
	)
	keys = {m.key for m in match_any_entries(f.any_of)}
	assert "allowed_group_ids" in keys
	assert "allowed_role_ids" in keys


def test_acl_filter_empty_groups_and_roles_no_match_any() -> None:
	f = acl_filter("note", is_admin=False, user_id="u1", group_ids=[], role_ids=())
	assert match_any_entries(f.any_of) == []


def test_acl_filter_tuple_and_list_group_ids_equivalent() -> None:
	f_list = acl_filter("note", is_admin=False, user_id="u1", group_ids=["g1"])
	f_tuple = acl_filter("note", is_admin=False, user_id="u1", group_ids=("g1",))
	list_entries = match_any_entries(f_list.any_of)
	tuple_entries = match_any_entries(f_tuple.any_of)
	assert list_entries[0].values == tuple_entries[0].values
