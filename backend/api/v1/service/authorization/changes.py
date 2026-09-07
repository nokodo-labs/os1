"""resolved access-change hooks and durable event enrichment."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.advisory_locks import acquire_resource_write_lock
from api.models.access_revision import AccessRevision
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.permissions import (
	AccessLevel,
	ResourceType,
)
from api.v1.service.authorization.cache import (
	resolve_accessible_user_ids,
	resolve_resource_access_user_ids,
)
from api.v1.service.authorization.config import (
	RESOURCE_CONFIG,
	is_acl_resource_config,
	resource_access_lock_namespace,
)
from api.v1.service.authorization.types import ResourceRef
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.typeid import TypeID


type _ResolvedUserIds = dict[
	tuple[ResourceType, TypeID, AccessLevel, bool, bool], frozenset[TypeID]
]
type _ResolvingAccess = set[tuple[ResourceType, TypeID, AccessLevel, bool, bool]]


@dataclass(frozen=True, slots=True)
class ResolvedAccessShape:
	"""who could reach one resource, at each level, at one point in time.

	NAMED, not a positional tuple indexed by an access level's rank. the two
	members answer different questions and the second is not a level at all, so
	an index arithmetic mistake - or a fourth `AccessLevel` member shifting the
	ranks - would silently hand the writer set to a security-relevant event
	audience with no visible symptom.
	"""

	#: accessible users per level, INCLUDING resource operators. the
	#: access-event audience is drawn from here at ``acl_list_visibility``.
	by_level: dict[AccessLevel, frozenset[TypeID]]
	#: users with resource-derived EDITOR, EXCLUDING operators: the "is this
	#: thread multi-writer" question, not an access level.
	derived_writers: frozenset[TypeID]


@dataclass(frozen=True, slots=True)
class AccessChangeEventEnrichment:
	"""domain-owned fields used to enrich one access event."""

	metadata: JSONObject = field(default_factory=dict)
	message_id: TypeID | None = None


type AccessChangeFinalizer = Callable[
	[
		AsyncSession,
		dict[ResourceRef, ResolvedAccessShape],
	],
	Awaitable[dict[ResourceRef, AccessChangeEventEnrichment]],
]
type AccessChangeHook = Callable[
	[
		list[ResourceRef],
		dict[ResourceRef, ResolvedAccessShape],
		AsyncSession,
	],
	Awaitable[AccessChangeFinalizer],
]


@dataclass(frozen=True, slots=True)
class AccessChangeSnapshot:
	"""captured event refs, affected maintenance refs, and hook finalizers."""

	captured_resource_refs: list[ResourceRef]
	affected_resource_refs: list[ResourceRef]
	finalizers: list[AccessChangeFinalizer]
	resolved_access: dict[ResourceRef, ResolvedAccessShape]


@dataclass(frozen=True, slots=True)
class PreparedAccessChange:
	"""one staged access event and its before-or-after recipients."""

	event: Event
	recipient_ids: list[TypeID]


@dataclass(frozen=True, slots=True)
class AccessChangeRecord:
	"""one persisted resolved-access revision."""

	revision: int
	metadata: JSONObject


@dataclass(frozen=True, slots=True)
class AccessChangeBatch:
	"""a contiguous range of persisted resolved-access revisions."""

	current_revision: int
	records: list[AccessChangeRecord]


_hooks: list[AccessChangeHook] = []


def register_access_change_hook(hook: AccessChangeHook) -> None:
	"""register one resolved-access event enrichment hook."""
	if hook not in _hooks:
		_hooks.append(hook)


async def capture_access_change(
	resource_refs: list[ResourceRef],
	session: AsyncSession,
) -> AccessChangeSnapshot:
	"""lock and capture the changed resources before a mutation.

	only the resources named by the caller are locked and resolved - never
	their descendants. a descendant's access answers are derived from these
	roots, so they are covered by the subtree marker on the emitted event and
	by ancestor-version validation in the accessible-users cache. cost is
	therefore independent of subtree size and needs no cap.
	"""
	affected_refs = list(dict.fromkeys(resource_refs))
	refs = [
		resource_ref
		for resource_ref in affected_refs
		if is_acl_resource_config(RESOURCE_CONFIG[resource_ref[0]])
	]
	for resource_type, resource_id in sorted(
		refs,
		key=lambda resource_ref: (
			resource_ref[0].value,
			str(resource_ref[1]),
		),
	):
		await acquire_resource_write_lock(
			session,
			resource_access_lock_namespace(resource_type),
			resource_id,
		)
	resolved_user_ids: _ResolvedUserIds = {}
	resolving_access: _ResolvingAccess = set()
	resolved_access = {
		resource_ref: await _resolved_access_shape(
			resource_ref,
			session,
			resolved_user_ids=resolved_user_ids,
			resolving_access=resolving_access,
		)
		for resource_ref in refs
	}
	return AccessChangeSnapshot(
		captured_resource_refs=refs,
		affected_resource_refs=affected_refs,
		finalizers=[await hook(refs, resolved_access, session) for hook in _hooks],
		resolved_access=resolved_access,
	)


async def build_access_change_events(
	snapshot: AccessChangeSnapshot,
	session: AsyncSession,
	actor_user_id: TypeID | None = None,
	data_by_resource: dict[ResourceRef, dict[str, JSONValue]] | None = None,
	after_access: dict[ResourceRef, ResolvedAccessShape] | None = None,
	forced_resource_refs: set[ResourceRef] | None = None,
) -> list[PreparedAccessChange]:
	"""build revisioned events for changed resolved-access facets.

	``data_by_resource`` supplies event PAYLOAD and nothing more; it does not
	decide whether an event happens. that separation matters because an event
	here costs an `AccessRevision` bump, which invalidates the ACL stamp on
	every vector chunk of the resource AND of every descendant - so a caller
	with a payload to attach must not accidentally schedule a subtree-wide
	resync for a change that moved nobody's access.

	``forced_resource_refs`` is the explicit opt-in for callers that know
	something changed which resolved access cannot see.
	"""
	resource_ref_set = set(snapshot.captured_resource_refs)
	if data_by_resource is not None and not set(data_by_resource) <= resource_ref_set:
		raise ValueError("access event data contains an uncaptured resource")
	if forced_resource_refs is not None and not (
		forced_resource_refs <= resource_ref_set
	):
		raise ValueError("forced access event contains an uncaptured resource")
	enrichment_by_resource: dict[ResourceRef, AccessChangeEventEnrichment] = {}
	if after_access is None:
		resolved_user_ids: _ResolvedUserIds = {}
		resolving_access: _ResolvingAccess = set()
		after_access = {
			resource_ref: await _resolved_access_shape(
				resource_ref,
				session,
				resolved_user_ids=resolved_user_ids,
				resolving_access=resolving_access,
			)
			for resource_ref in snapshot.captured_resource_refs
		}
	for finalize in snapshot.finalizers:
		finalized = await finalize(session, after_access)
		if not set(finalized) <= resource_ref_set:
			raise ValueError("access event enrichment contains an uncaptured resource")
		for resource_ref, enrichment in finalized.items():
			previous = enrichment_by_resource.get(resource_ref)
			enrichment_by_resource[resource_ref] = AccessChangeEventEnrichment(
				metadata={
					**(previous.metadata if previous is not None else {}),
					**enrichment.metadata,
				},
				message_id=(
					enrichment.message_id
					if enrichment.message_id is not None
					else (previous.message_id if previous is not None else None)
				),
			)

	prepared: list[PreparedAccessChange] = []
	changed_resources = {
		resource_ref
		for resource_ref in snapshot.captured_resource_refs
		if snapshot.resolved_access[resource_ref] != after_access[resource_ref]
	}
	if forced_resource_refs is not None:
		changed_resources.update(forced_resource_refs)
	for resource_ref in snapshot.captured_resource_refs:
		if resource_ref not in changed_resources:
			continue
		enrichment = enrichment_by_resource.get(
			resource_ref,
			AccessChangeEventEnrichment(),
		)
		resource_type, resource_id = resource_ref
		revision_row = await session.get(AccessRevision, resource_ref)
		if revision_row is None:
			revision_row = AccessRevision(
				resource_type=resource_type,
				resource_id=resource_id,
				revision=1,
			)
			session.add(revision_row)
		else:
			revision_row.revision += 1
		data: dict[str, JSONValue] = {
			"resource_type": resource_type.value,
			"resource_id": str(resource_id),
			"revision": revision_row.revision,
			# the event covers this resource AND everything inheriting from it;
			# no per-descendant event is emitted, at any subtree size.
			"subtree": True,
			"changes": [],
		}
		if enrichment.message_id is not None:
			data["message_id"] = str(enrichment.message_id)
		if data_by_resource is not None:
			data.update(data_by_resource.get(resource_ref, {}))
		event = Event(
			scope=(
				EventScope.THREAD
				if resource_type == ResourceType.THREAD
				else EventScope.SYSTEM
			),
			scope_id=resource_id,
			type=EventType.ACCESS_UPDATED,
			data=data,
			resource_revision=revision_row.revision,
			user_id=actor_user_id,
			thread_id=(resource_id if resource_type == ResourceType.THREAD else None),
			metadata_=enrichment.metadata,
		)
		session.add(event)
		visibility = RESOURCE_CONFIG[resource_type].acl_list_visibility
		prepared.append(
			PreparedAccessChange(
				event=event,
				recipient_ids=list(
					dict.fromkeys(
						[
							*snapshot.resolved_access[resource_ref].by_level[
								visibility
							],
							*after_access[resource_ref].by_level[visibility],
						]
					)
				),
			)
		)
	return prepared


async def _resolved_access_shape(
	resource_ref: ResourceRef,
	session: AsyncSession,
	resolved_user_ids: _ResolvedUserIds | None = None,
	resolving_access: _ResolvingAccess | None = None,
) -> ResolvedAccessShape:
	"""resolve access-level user sets for one resource."""
	resource_type, resource_id = resource_ref
	return ResolvedAccessShape(
		by_level={
			level: frozenset(
				await resolve_accessible_user_ids(
					resource_type,
					resource_id,
					session,
					required_level=level,
					resolved_user_ids=resolved_user_ids,
					resolving_access=resolving_access,
				)
			)
			for level in AccessLevel
		},
		derived_writers=frozenset(
			await resolve_resource_access_user_ids(
				resource_type,
				resource_id,
				session,
				required_level=AccessLevel.EDITOR,
				resolved_user_ids=resolved_user_ids,
				resolving_access=resolving_access,
			)
		),
	)


async def current_access_revision(
	resource_ref: ResourceRef,
	session: AsyncSession,
) -> int:
	"""return the latest resolved-access event revision for one resource."""
	return (
		await session.scalar(
			select(AccessRevision.revision).where(
				AccessRevision.resource_type == resource_ref[0],
				AccessRevision.resource_id == resource_ref[1],
			)
		)
		or 0
	)


async def read_access_change_batch(
	resource_ref: ResourceRef,
	after_revision: int,
	session: AsyncSession,
) -> AccessChangeBatch:
	"""return revisions; ACCESS_UPDATED rows must survive their revision row."""
	current_revision = await current_access_revision(resource_ref, session)
	if current_revision <= after_revision:
		return AccessChangeBatch(current_revision=current_revision, records=[])
	resource_type, resource_id = resource_ref
	events = list(
		await session.scalars(
			select(Event)
			.where(
				Event.type == EventType.ACCESS_UPDATED,
				Event.scope_id == resource_id,
				Event.resource_revision > after_revision,
				Event.resource_revision <= current_revision,
				Event.data["resource_type"].as_string() == resource_type.value,
			)
			.order_by(Event.resource_revision)
		)
	)
	if len(events) != current_revision - after_revision:
		raise RuntimeError(
			f"access revision gap for {resource_type.value} {resource_id}"
		)
	records: list[AccessChangeRecord] = []
	expected_revision = after_revision + 1
	for event in events:
		if event.resource_revision != expected_revision:
			raise RuntimeError(
				f"access revision gap for {resource_type.value} {resource_id}"
			)
		records.append(
			AccessChangeRecord(
				revision=expected_revision,
				metadata=event.public_metadata,
			)
		)
		expected_revision += 1
	return AccessChangeBatch(
		current_revision=current_revision,
		records=records,
	)
