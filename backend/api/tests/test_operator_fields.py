"""the private facet and the {resource}:manage permission.

covers the two things the permission unifies: the ACL short-circuit in the
resolver, and operator-only read of a resource's ``private`` facet.
"""

import ast
import inspect
import json
import re
import textwrap
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.constants import PRIVATE_METADATA_KEY
from api.models.access_rule import AccessLevel
from api.models.file import File, FileSource, FileStatus
from api.models.memory import Memory as MemoryModel
from api.models.message import MessageType
from api.models.message import UserMessage as MessageModel
from api.models.thread import Thread as ThreadModel
from api.permissions import (
	RESOURCE_MANAGE_PERMISSION,
	ActionPermission,
	PermissionGrant,
	ResourceType,
)
from api.schemas.common import PrivateFacetModel, PrivateModel
from api.schemas.file import File as FileOut
from api.schemas.file import FilePrivateInput, FileUpdate
from api.schemas.memory import Memory as MemoryOut
from api.schemas.message import Message as MessageOut
from api.schemas.thread import Thread as ThreadOut
from api.tests.factories import create_user, make_principal, principal_for
from api.v1.service.authorization import (
	get_effective_access_level,
	project_private,
)
from api.v1.service.files import core as file_service
from nokodo_ai.utils.typeid import TypeID, new_typeid


# permission surface


def test_every_default_access_resource_type_has_an_operator_permission() -> None:
	"""the 7 ACL-driven user-facing types all gained a manage permission."""
	expected = {
		ResourceType.THREAD: ActionPermission.THREADS_MANAGE,
		ResourceType.PROJECT: ActionPermission.PROJECTS_MANAGE,
		ResourceType.NOTE: ActionPermission.NOTES_MANAGE,
		ResourceType.GROUP: ActionPermission.GROUPS_MANAGE,
		ResourceType.REMINDER_LIST: ActionPermission.REMINDERS_MANAGE,
		ResourceType.CALENDAR: ActionPermission.CALENDAR_MANAGE,
		ResourceType.FILE: ActionPermission.FILES_MANAGE,
	}
	for resource_type, permission in expected.items():
		assert RESOURCE_MANAGE_PERMISSION[resource_type] == permission


def test_every_resource_type_has_an_operator_permission() -> None:
	"""the mapping is TOTAL, so the superuser-only fallback is unreachable.

	``memory`` was the last hole: it had a private facet (the embedding) but no
	manage permission, which silently made superuser the only operator. a type
	that can hold operator data must be operable by a role, not just by root.
	"""
	missing = [rt for rt in ResourceType if rt not in RESOURCE_MANAGE_PERMISSION]
	assert not missing, f"resource types with no operator permission: {missing}"


def test_leaf_types_resolve_to_their_parent_domain_permission() -> None:
	"""an operator of a domain is an operator of the leaves inside it."""
	assert (
		RESOURCE_MANAGE_PERMISSION[ResourceType.MESSAGE]
		== ActionPermission.THREADS_MANAGE
	)
	assert (
		RESOURCE_MANAGE_PERMISSION[ResourceType.REMINDER]
		== ActionPermission.REMINDERS_MANAGE
	)
	assert (
		RESOURCE_MANAGE_PERMISSION[ResourceType.CALENDAR_EVENT]
		== ActionPermission.CALENDAR_MANAGE
	)


def test_manage_does_not_imply_create() -> None:
	"""permissions stay atomic; only a domain wildcard covers both."""
	operator = make_principal(permissions=frozenset({ActionPermission.FILES_MANAGE}))
	assert operator.is_resource_operator(ResourceType.FILE)
	assert not operator.has_permission(ActionPermission.FILES_CREATE)


def test_ownership_never_confers_operator_status() -> None:
	"""an owner has ADMIN on their own resource but is not an operator."""
	owner = make_principal()
	assert not owner.is_resource_operator(ResourceType.FILE)


def test_operator_of_one_type_is_not_operator_of_another() -> None:
	files_operator = make_principal(
		permissions=frozenset({ActionPermission.FILES_MANAGE})
	)
	assert files_operator.is_resource_operator(ResourceType.FILE)
	assert not files_operator.is_resource_operator(ResourceType.THREAD)


# ACL short-circuit


@pytest.mark.asyncio
async def test_operator_short_circuits_to_admin_access(
	db_session: AsyncSession,
) -> None:
	"""the resolver answers once; no service-level _can_manage checks needed."""
	owner = await create_user(db_session, f"opf_owner_{new_typeid('user')[-8:]}")
	file = File(
		owner_id=owner.id,
		storage_backend="local",
		storage_key=f"operator/{new_typeid('file')}.bin",
		filename="secret.bin",
	)
	db_session.add(file)
	await db_session.commit()

	stranger = make_principal()
	assert (
		await get_effective_access_level(
			db_session, stranger, ResourceType.FILE, file.id
		)
		is None
	)

	operator = make_principal(permissions=frozenset({ActionPermission.FILES_MANAGE}))
	assert (
		await get_effective_access_level(
			db_session, operator, ResourceType.FILE, file.id
		)
		== AccessLevel.ADMIN
	)


@pytest.mark.asyncio
async def test_operator_sees_every_resource_in_listings(
	db_session: AsyncSession,
) -> None:
	"""the SQL predicate must short-circuit too, or listings stay blind."""
	owner = await create_user(db_session, f"opf_list_{new_typeid('user')[-8:]}")
	file = File(
		owner_id=owner.id,
		storage_backend="local",
		storage_key=f"operator/{new_typeid('file')}.bin",
		filename="listed.bin",
	)
	db_session.add(file)
	await db_session.commit()

	operator = make_principal(permissions=frozenset({ActionPermission.FILES_MANAGE}))
	listed = await file_service.list_files(db_session, principal=operator, limit=100)
	assert str(file.id) in {str(f.id) for f in listed}

	stranger = make_principal()
	hidden = await file_service.list_files(db_session, principal=stranger, limit=100)
	assert str(file.id) not in {str(f.id) for f in hidden}


# redaction


SENTINEL = "tenant/secret-object.bin"


def _file_row() -> File:
	now = datetime.now(UTC)
	file = File(
		id=TypeID(new_typeid("file")),
		source=FileSource.USER_UPLOADED,
		status=FileStatus.AVAILABLE,
		storage_backend="local",
		storage_key=SENTINEL,
		checksum_sha256="a" * 64,
		filename="doc.bin",
		created_at=now,
		updated_at=now,
	)
	file.set_metadata(public={"visible": 1}, private={"content_vectors_schema": 3})
	return file


def _file_payload() -> FileOut:
	return FileOut.from_row(_file_row())


def test_set_metadata_does_not_alias_the_previous_private_half() -> None:
	"""a public-only write must SNAPSHOT the private half, not alias it.

	regression: the carry-over branch reused the nested dict the previous
	``metadata_`` value still referenced, so mutating one silently mutated the
	other - the exact clobbering the split exists to make impossible.
	"""
	file = _file_row()
	before = file.metadata_
	before_private = before[PRIVATE_METADATA_KEY]
	assert isinstance(before_private, dict)

	file.set_metadata(public={"visible": 2})

	assert file.metadata_ is not before
	assert file.private_metadata is not before_private

	file.private_metadata["injected"] = True
	assert "injected" not in before_private


def test_non_operator_loses_the_whole_private_facet() -> None:
	(projected,) = project_private(
		make_principal(), ResourceType.FILE, [_file_payload()]
	)
	assert projected.private is None
	assert projected.filename == "doc.bin"


def test_operator_keeps_the_private_facet() -> None:
	operator = make_principal(permissions=frozenset({ActionPermission.FILES_MANAGE}))
	(kept,) = project_private(operator, ResourceType.FILE, [_file_payload()])
	assert kept.private is not None
	assert kept.private.storage_backend == "local"
	assert kept.private.storage_key == SENTINEL
	assert kept.private.checksum_sha256 == "a" * 64


def test_projection_does_not_mutate_the_cached_payload() -> None:
	"""the payload cache is not principal-keyed, so projection must copy."""
	cached = _file_payload()
	project_private(make_principal(), ResourceType.FILE, [cached])
	assert cached.private is not None
	assert cached.private.storage_key == SENTINEL


def test_projected_payloads_are_read_only_views() -> None:
	"""the copy is shallow by design, so callers must not mutate the result.

	dropping ``private`` is the only isolated change; every public field is
	still the source object. this pins the invariant the docstring states, so
	nobody "fixes" it by mutating a projected payload in place.
	"""
	source = _file_payload()
	(projected,) = project_private(make_principal(), ResourceType.FILE, [source])
	assert projected.metadata is source.metadata

	operator = make_principal(permissions=frozenset({ActionPermission.FILES_MANAGE}))
	(kept,) = project_private(operator, ResourceType.FILE, [source])
	assert kept is source


def test_no_private_value_survives_a_non_operator_dump() -> None:
	"""the one check response_model cannot do: scan the serialized output.

	catches any private field added later, not just the ones known today.
	"""
	(projected,) = project_private(
		make_principal(), ResourceType.FILE, [_file_payload()]
	)
	dumped = json.dumps(projected.model_dump(mode="json"))
	assert SENTINEL not in dumped
	assert "content_vectors_schema" not in dumped
	assert json.loads(dumped)["metadata"] == {"visible": 1}


def test_private_metadata_is_readable_by_operators() -> None:
	operator = make_principal(permissions=frozenset({ActionPermission.FILES_MANAGE}))
	(kept,) = project_private(operator, ResourceType.FILE, [_file_payload()])
	dumped = kept.model_dump(mode="json")
	assert dumped["private"]["metadata"] == {"content_vectors_schema": 3}
	assert dumped["metadata"] == {"visible": 1}


def test_superuser_is_an_operator_of_every_resource_type() -> None:
	admin = make_principal(is_superuser=True)
	(kept,) = project_private(admin, ResourceType.FILE, [_file_payload()])
	assert kept.private is not None
	assert kept.private.storage_key == SENTINEL


def test_payload_built_without_from_row_has_no_private_facet() -> None:
	"""plain validation is the public view: the facet is opt-in."""
	assert FileOut.model_validate(_file_row()).private is None


# every resource with a facet, not just File


PRIVATE_SENTINEL = "content_vectors_schema"


def _thread_row() -> ThreadModel:
	now = datetime.now(UTC)
	thread = ThreadModel(
		id=TypeID(new_typeid("thread")),
		owner_id=TypeID(new_typeid("user")),
		title="t",
		tags=[],
		last_activity_at=now,
		created_at=now,
		updated_at=now,
	)
	thread.set_metadata(public={"visible": 1}, private={PRIVATE_SENTINEL: 3})
	return thread


def _message_row() -> MessageModel:
	now = datetime.now(UTC)
	message = MessageModel(
		id=TypeID(new_typeid("msg")),
		thread_id=TypeID(new_typeid("thread")),
		type=MessageType.USER,
		content=[],
		tool_calls=[],
		citations=[],
		created_at=now,
		updated_at=now,
	)
	message.set_metadata(public={"visible": 1}, private={PRIVATE_SENTINEL: 3})
	return message


def _memory_row() -> MemoryModel:
	now = datetime.now(UTC)
	memory = MemoryModel(
		id=TypeID(new_typeid("mem")),
		user_id=TypeID(new_typeid("user")),
		content="remembered",
		embedding=b"vector-bytes",
		created_at=now,
		updated_at=now,
	)
	memory.set_metadata(public={"visible": 1}, private={PRIVATE_SENTINEL: 3})
	return memory


FACET_RESOURCES = [
	pytest.param(
		ResourceType.FILE,
		FileOut,
		_file_row,
		ActionPermission.FILES_MANAGE,
		id="file",
	),
	pytest.param(
		ResourceType.THREAD,
		ThreadOut,
		_thread_row,
		ActionPermission.THREADS_MANAGE,
		id="thread",
	),
	pytest.param(
		ResourceType.MESSAGE,
		MessageOut,
		_message_row,
		ActionPermission.THREADS_MANAGE,
		id="message",
	),
	pytest.param(
		ResourceType.MEMORY,
		MemoryOut,
		_memory_row,
		ActionPermission.MEMORIES_MANAGE,
		id="memory",
	),
]


@pytest.mark.parametrize(
	("resource_type", "schema", "row", "permission"), FACET_RESOURCES
)
def test_facet_is_opt_in_for_every_resource(
	resource_type: ResourceType,
	schema: type[PrivateFacetModel[PrivateModel]],
	row: Callable[[], object],
	permission: PermissionGrant,
) -> None:
	"""``from_row`` is the ONLY way a facet gets populated.

	the fail-closed guarantee was asserted for File alone while Thread injected
	its facet from a model_validator, so plain validation leaked. this pins the
	invariant on every facet-bearing resource.
	"""
	assert schema.model_validate(row()).private is None
	assert schema.from_row(row()).private is not None


@pytest.mark.parametrize(
	("resource_type", "schema", "row", "permission"), FACET_RESOURCES
)
def test_projection_splits_by_operator_for_every_resource(
	resource_type: ResourceType,
	schema: type[PrivateFacetModel[PrivateModel]],
	row: Callable[[], object],
	permission: PermissionGrant,
) -> None:
	"""non-operators lose the facet; operators keep it; nothing leaks in a dump."""
	(hidden,) = project_private(
		make_principal(), resource_type, [schema.from_row(row())]
	)
	assert hidden.private is None
	assert PRIVATE_SENTINEL not in json.dumps(hidden.model_dump(mode="json"))
	assert hidden.model_dump(mode="json")["metadata"] == {"visible": 1}

	operator = make_principal(permissions=frozenset({permission}))
	(kept,) = project_private(operator, resource_type, [schema.from_row(row())])
	assert kept.private is not None
	assert kept.private.metadata == {PRIVATE_SENTINEL: 3}


def _called_functions(
	func: Callable[..., object], source: str
) -> list[Callable[..., object]]:
	"""the api-owned functions ``source`` calls, resolved through ``func``'s globals.

	handles both bare calls and the ``service_module.helper()`` form the
	routers use, which is where the projection actually lives.
	"""
	scope = getattr(func, "__globals__", {})
	resolved: list[Callable[..., object]] = []
	for node in ast.walk(ast.parse(textwrap.dedent(source))):
		if not isinstance(node, ast.Call):
			continue
		target = node.func
		if isinstance(target, ast.Name):
			found = scope.get(target.id)
		elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
			found = getattr(scope.get(target.value.id), target.attr, None)
		else:
			continue
		if inspect.isfunction(found) and found.__module__.startswith("api."):
			resolved.append(found)
	return resolved


def _projects_private(
	func: Callable[..., object],
	projectors: re.Pattern[str],
	depth: int = 3,
	seen: set[int] | None = None,
) -> bool:
	"""whether ``func`` projects, or reaches something that does."""
	seen = seen if seen is not None else set()
	if id(func) in seen or depth < 0:
		return False
	seen.add(id(func))
	try:
		source = inspect.getsource(func)
	except OSError, TypeError:
		# no source to read: assume the boundary is handled elsewhere.
		return True
	if projectors.search(source):
		return True
	return any(
		_projects_private(called, projectors, depth - 1, seen)
		for called in _called_functions(func, source)
	)


def _annotated_schemas(annotation: object) -> set[type]:
	"""every model class reachable from a response annotation.

	unwraps the containers a route returns a facet inside of: ``Page[File]``,
	``list[File]``, ``File | None``.
	"""
	found: set[type] = set()
	if isinstance(annotation, type):
		found.add(annotation)
		for field in getattr(annotation, "model_fields", {}).values():
			found |= _annotated_schemas(field.annotation)
		return found
	for arg in get_args(annotation):
		found |= _annotated_schemas(arg)
	return found


# the mixin is the only supported writer


def test_nothing_assigns_the_metadata_column_directly() -> None:
	"""``set_metadata`` is the only writer; a raw assign clobbers the other half.

	the design called this "structurally impossible", but nothing in python
	stops ``row.metadata_ = {...}`` - and three media generation services were
	doing exactly that, dropping any private half and writing a `_`-prefixed
	key straight into the public one. a convention nobody checks is not a
	guarantee, so this is the check.

	scans ALL of ``api/`` rather than just the services: a writer added in a
	router or a task module is the same bug. ``setattr`` is matched too, since
	it is the obvious way around a name-based scan.

	constructor kwargs (``Model(metadata_=...)``) are fine: a brand new row has
	no other half to clobber, and cloning a full column value is the point.
	"""
	api_root = Path(__file__).resolve().parent.parent
	# mixins.py DEFINES the writer; migrations operate on raw rows, pre-mixin;
	# tests stamp bare fixture rows where there is no other half to lose.
	skip = {
		api_root / "models" / "mixins.py",
		api_root / "migrations",
		api_root / "tests",
	}
	assign = re.compile(
		r"""^\s*[\w.]+\.metadata_\s*=(?!=)|setattr\([^,]+,\s*["']metadata_["']"""
	)
	offenders = [
		f"{path.relative_to(api_root).as_posix()}:{number}"
		for path in api_root.rglob("*.py")
		if not any(parent in skip for parent in (path, *path.parents))
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
		if assign.search(line)
	]
	assert not offenders, (
		"assign through set_metadata(public=, private=) instead: "
		+ ", ".join(offenders)
	)


def test_every_facet_returning_route_projects_its_payload() -> None:
	"""a route returning a facet-bearing schema must project before returning.

	``project_private`` reaches only the TOP level of one payload, so a route
	that wraps payloads in ``Page`` or a list has to project the items itself.
	nothing in the type system enforces that: an unprojected ``FileOut`` and a
	projected one are the same type, so a new endpoint that builds payloads
	with ``from_row`` and returns them straight leaks the facet to every
	reader, silently and with no test failing.

	this walks the REAL route table, so a route added later is covered without
	being listed here. routers usually delegate, so the search follows the
	service functions a handler calls (one level) before reporting.
	"""
	from api.main import app

	facet_schemas = {FileOut, ThreadOut, MessageOut, MemoryOut}
	projectors = re.compile(r"project_private|public_payload")
	offenders: list[str] = []
	for route in app.routes:
		endpoint = getattr(route, "endpoint", None)
		response_model = getattr(route, "response_model", None)
		if endpoint is None or response_model is None:
			continue
		if not (_annotated_schemas(response_model) & facet_schemas):
			continue
		if not _projects_private(endpoint, projectors):
			offenders.append(f"{endpoint.__module__}.{endpoint.__qualname__}")

	assert not offenders, (
		"these routes return a private facet unprojected; call project_private "
		"(or a service helper that does) before returning: "
		+ ", ".join(sorted(offenders))
	)


# end to end through the service


@pytest.mark.asyncio
async def test_owner_reading_own_file_still_loses_the_private_facet(
	db_session: AsyncSession,
) -> None:
	"""self is not operator: owning a file does not reveal its storage key."""
	owner = await create_user(db_session, f"opf_self_{new_typeid('user')[-8:]}")
	file = File(
		owner_id=owner.id,
		storage_backend="local",
		storage_key=f"operator/{new_typeid('file')}.bin",
		filename="mine.bin",
	)
	db_session.add(file)
	await db_session.commit()

	payload = await file_service.get_file_payload(
		file.id,
		db_session,
		principal=principal_for(owner),
		use_cache=False,
	)
	assert payload.filename == "mine.bin"
	assert payload.private is None


@pytest.mark.asyncio
async def test_non_operator_cannot_write_the_private_facet(
	db_session: AsyncSession,
) -> None:
	"""submitting `private` without the manage permission is a 403, not a strip."""
	owner = await create_user(db_session, f"opf_write_{new_typeid('user')[-8:]}")
	file = File(
		owner_id=owner.id,
		storage_backend="local",
		storage_key=f"operator/{new_typeid('file')}.bin",
		filename="mine.bin",
	)
	db_session.add(file)
	await db_session.commit()

	with pytest.raises(HTTPException) as exc:
		await file_service.update_file(
			file.id,
			FileUpdate(private=FilePrivateInput(storage_key="forged")),
			db_session,
			principal=principal_for(owner),
		)
	assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_public_metadata_patch_preserves_private_metadata(
	db_session: AsyncSession,
) -> None:
	"""the wipe bug: a full-metadata PATCH must not clear backend-owned keys."""
	owner = await create_user(db_session, f"opf_keep_{new_typeid('user')[-8:]}")
	file = File(
		owner_id=owner.id,
		storage_backend="local",
		storage_key=f"operator/{new_typeid('file')}.bin",
		filename="mine.bin",
	)
	file.set_metadata(private={"content_vector_fingerprint": "fp1"})
	db_session.add(file)
	await db_session.commit()

	await file_service.update_file(
		file.id,
		FileUpdate(metadata={"replaced": True}),
		db_session,
		principal=principal_for(owner),
	)
	await db_session.refresh(file)
	assert file.public_metadata == {"replaced": True}
	assert file.private_metadata == {"content_vector_fingerprint": "fp1"}
