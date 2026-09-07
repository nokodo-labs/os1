"""accessible-user cache and recipient expansion for ACL resources."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from api.database.main import has_uncommitted_writes, session_scope
from api.database.post_commit import enqueue_post_commit_action
from api.models.access_rule import AccessRule
from api.models.role import Role
from api.models.user import User
from api.permissions import AccessLevel, ResourceType
from api.redis import cache
from api.settings import settings
from api.v1.service.authorization.config import (
	MAX_INHERITANCE_DEPTH,
	RESOURCE_CONFIG,
	default_access_resource_types,
	is_acl_resource_config,
)
from api.v1.service.authorization.inheritance import (
	affected_resource_types,
	load_parent_resource_refs,
)
from api.v1.service.authorization.predicates import (
	direct_resource_access_predicate,
	resource_operator_predicate,
)
from api.v1.service.authorization.types import ResourceRef
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _CachedUserIds:
	"""one cached answer plus the ancestor versions it was computed from."""

	user_ids: list[TypeID]
	ancestor_versions: dict[str, int]


def _cached_typeids(value: object) -> list[TypeID] | None:
	"""parse a cached ID list, returning None for any unexpected shape."""
	if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
		return None
	return [TypeID(item) for item in value]


def _cached_entry(value: object) -> _CachedUserIds | None:
	"""parse a cached accessible-users entry, returning None for any bad shape."""
	if not isinstance(value, dict):
		return None
	user_ids = _cached_typeids(value.get("user_ids"))
	if user_ids is None:
		return None
	raw_ancestors = value.get("ancestors")
	if not isinstance(raw_ancestors, dict):
		return None
	ancestor_versions: dict[str, int] = {}
	for key, version in raw_ancestors.items():
		if not isinstance(key, str) or not isinstance(version, int):
			return None
		ancestor_versions[key] = version
	return _CachedUserIds(user_ids=user_ids, ancestor_versions=ancestor_versions)


def _accessible_users_version_key(
	resource_type: ResourceType,
	resource_id: TypeID,
) -> str:
	return f"accessible_users_version:{resource_type.value}:{resource_id}"


def _accessible_users_type_version_key(resource_type: ResourceType) -> str:
	return f"accessible_users_type_version:{resource_type.value}"


async def _cache_versions(
	resource_type: ResourceType,
	resource_id: TypeID,
) -> tuple[int, int] | None:
	type_version, resource_version = await cache.get_many(
		[
			_accessible_users_type_version_key(resource_type),
			_accessible_users_version_key(resource_type, resource_id),
		]
	)
	if type_version is not None and not isinstance(type_version, int):
		return None
	if resource_version is not None and not isinstance(resource_version, int):
		return None
	return (
		type_version if isinstance(type_version, int) else 0,
		resource_version if isinstance(resource_version, int) else 0,
	)


async def _current_ancestor_versions(keys: list[str]) -> dict[str, int] | None:
	"""read the current version of every recorded ancestor in one round trip."""
	if not keys:
		return {}
	values = await cache.get_many(keys)
	versions: dict[str, int] = {}
	for key, value in zip(keys, values, strict=True):
		if value is not None and not isinstance(value, int):
			return None
		versions[key] = value if isinstance(value, int) else 0
	return versions


async def _record_versions(
	resource_refs: list[ResourceRef],
	consulted_refs: dict[ResourceRef, int] | None,
) -> None:
	"""stamp versions for refs the walk is about to consult, in one round trip.

	read BEFORE the rows they describe, so a bump racing the resolve lands
	after the stamp and is caught by the post-resolve re-read. batched per
	frame rather than per ancestor: a wide parent set would otherwise cost one
	GET each.
	"""
	if consulted_refs is None:
		return
	pending = [ref for ref in dict.fromkeys(resource_refs) if ref not in consulted_refs]
	if not pending:
		return
	values = await cache.get_many(
		[
			_accessible_users_version_key(resource_type, resource_id)
			for resource_type, resource_id in pending
		]
	)
	for ref, value in zip(pending, values, strict=True):
		consulted_refs[ref] = value if isinstance(value, int) else 0


type _UserIdResolver = Callable[
	[ResourceType, TypeID, AsyncSession, AccessLevel, dict[ResourceRef, int] | None],
	Awaitable[list[TypeID]],
]


async def _list_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession | None,
	required_level: AccessLevel,
	key_prefix: str,
	resolver: _UserIdResolver,
	warning: str,
) -> list[TypeID]:
	"""return a cached or freshly resolved answer, validated against ancestors.

	an ACL change bumps only the changed resource's version, so a cached entry is
	valid only while every ancestor it was computed from still carries the version
	recorded at fill time. that keeps invalidation O(1) in the size of a
	resource's subtree while still expiring every answer that depended on it.

	the stored versions are the ones read BEFORE the resolve, and every one is
	re-read after: an ancestor bumped while the resolve was in flight would
	otherwise be stamped with its new version, leaving an entry computed from
	stale data validating as fresh. any movement discards the entry instead.

	a FILL only ever reads committed state. a borrowed session may hold flushed
	but uncommitted rows - a caller that reparented a resource and then asks who
	can reach it is the ordinary shape - and an entry computed from work that
	later rolls back would survive the rollback under an unbumped version key
	for the full TTL. so a borrowed session serves the cached-hit path and the
	caller's own answer, and the resolve that gets STORED runs on a fresh
	session. the ancestor-version machinery defends against ancestors moving
	during a resolve; it has no defence against data that never lands.
	"""
	async with session_scope(session) as db:
		versions = await _cache_versions(resource_type, resource_id)
		if versions is None:
			return await resolver(resource_type, resource_id, db, required_level, None)
		type_version, resource_version = versions
		cache_key = (
			f"{key_prefix}:{resource_type.value}:{resource_id}:"
			f"{required_level.value}:{type_version}:{resource_version}"
		)
		cached = _cached_entry(await cache.get(cache_key))
		if cached is not None:
			current = await _current_ancestor_versions(list(cached.ancestor_versions))
			if current is not None and current == cached.ancestor_versions:
				return cached.user_ids
		if session is not None and has_uncommitted_writes(db):
			# the caller gets the answer their own transaction implies, and
			# nothing is published from it.
			return await resolver(resource_type, resource_id, db, required_level, None)
		# the resolver records each ancestor's version before reading its rows, so
		# the stamp always predates the data it describes.
		consulted: dict[ResourceRef, int] = {}
		result = await resolver(
			resource_type,
			resource_id,
			db,
			required_level,
			consulted,
		)
		# no sorting: this dict is compared with `!=` and round-tripped through
		# JSON as an object, so key order never participates in any decision.
		snapshot = {
			_accessible_users_version_key(ancestor_type, ancestor_id): version
			for (ancestor_type, ancestor_id), version in consulted.items()
			if (ancestor_type, ancestor_id) != (resource_type, resource_id)
		}
		after = await _current_ancestor_versions(list(snapshot))
		if after is None or after != snapshot:
			# an ancestor moved while resolving: this answer may already be stale
			return result
		written = await cache.set(
			cache_key,
			{
				"user_ids": [str(uid) for uid in result],
				"ancestors": snapshot,
			},
			ttl=settings.cache.accessible_users_ttl_seconds,
		)
		if not written:
			logger.warning(warning, resource_type.value, resource_id)
		return result


async def _list_accessible_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession | None,
	required_level: AccessLevel = AccessLevel.READER,
) -> list[TypeID]:
	"""return users with access to one resource, using its cache entry."""
	return await _list_user_ids(
		resource_type,
		resource_id,
		session,
		required_level,
		"accessible_users",
		_resolve_accessible_user_ids_for_cache,
		"accessible-user cache write failed for %s %s",
	)


async def _list_resource_access_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession | None,
	required_level: AccessLevel = AccessLevel.READER,
) -> list[TypeID]:
	"""return resource-derived users for one resource, using its cache entry."""
	return await _list_user_ids(
		resource_type,
		resource_id,
		session,
		required_level,
		"resource_access_users",
		_resolve_resource_access_user_ids_for_cache,
		"resource-access user cache write failed for %s %s",
	)


async def _resolve_accessible_user_ids_for_cache(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel,
	consulted_refs: dict[ResourceRef, int] | None,
) -> list[TypeID]:
	return await resolve_accessible_user_ids(
		resource_type,
		resource_id,
		session,
		required_level,
		consulted_refs=consulted_refs,
	)


async def _resolve_resource_access_user_ids_for_cache(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel,
	consulted_refs: dict[ResourceRef, int] | None,
) -> list[TypeID]:
	return await resolve_resource_access_user_ids(
		resource_type,
		resource_id,
		session,
		required_level,
		consulted_refs=consulted_refs,
	)


async def list_accessible_user_ids_for_resources(
	resource_refs: list[ResourceRef],
	session: AsyncSession | None,
	required_level: AccessLevel = AccessLevel.READER,
) -> list[TypeID]:
	"""return users who can access any resource in the list."""
	result: list[TypeID] = []
	seen: set[str] = set()
	for resource_type, resource_id in resource_refs:
		for user_id in await _list_accessible_user_ids(
			resource_type,
			resource_id,
			session,
			required_level,
		):
			key = str(user_id)
			if key not in seen:
				seen.add(key)
				result.append(user_id)
	return result


async def list_resource_access_user_ids_for_resources(
	resource_refs: list[ResourceRef],
	session: AsyncSession | None,
	required_level: AccessLevel = AccessLevel.READER,
) -> list[TypeID]:
	"""return users with resource-derived access to any resource in the list."""
	result: list[TypeID] = []
	seen: set[str] = set()
	for resource_type, resource_id in resource_refs:
		for user_id in await _list_resource_access_user_ids(
			resource_type,
			resource_id,
			session,
			required_level,
		):
			key = str(user_id)
			if key not in seen:
				seen.add(key)
				result.append(user_id)
	return result


async def resolve_accessible_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel = AccessLevel.READER,
	resolved_user_ids: dict[
		tuple[ResourceType, TypeID, AccessLevel, bool, bool], frozenset[TypeID]
	]
	| None = None,
	resolving_access: set[tuple[ResourceType, TypeID, AccessLevel, bool, bool]]
	| None = None,
	consulted_refs: dict[ResourceRef, int] | None = None,
) -> list[TypeID]:
	"""freshly resolve active users with effective access, including operators."""
	return await _resolve_accessible_user_ids(
		resource_type,
		resource_id,
		session,
		required_level,
		include_operators=True,
		resolved_user_ids=resolved_user_ids,
		resolving_access=resolving_access,
		consulted_refs=consulted_refs,
	)


async def resolve_resource_access_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel = AccessLevel.READER,
	resolved_user_ids: dict[
		tuple[ResourceType, TypeID, AccessLevel, bool, bool], frozenset[TypeID]
	]
	| None = None,
	resolving_access: set[tuple[ResourceType, TypeID, AccessLevel, bool, bool]]
	| None = None,
	consulted_refs: dict[ResourceRef, int] | None = None,
) -> list[TypeID]:
	"""freshly resolve active users with resource-derived access only."""
	return await _resolve_accessible_user_ids(
		resource_type,
		resource_id,
		session,
		required_level,
		include_operators=False,
		resolved_user_ids=resolved_user_ids,
		resolving_access=resolving_access,
		consulted_refs=consulted_refs,
	)


async def invalidate_accessible_users_for_resource(
	resource_type: ResourceType,
	resource_id: TypeID,
) -> None:
	"""invalidate accessible-user entries computed from one resource.

	only this resource's version is bumped. entries for resources that inherit
	from it recorded its version when they were filled, so they self-invalidate
	on their next read - no descendant walk, at any subtree size.
	"""
	await _invalidate_resource_refs([(resource_type, resource_id)])


async def invalidate_accessible_users_for_refs(
	resource_refs: list[ResourceRef],
) -> None:
	"""invalidate accessible-user entries for concrete resources."""
	await _invalidate_resource_refs(resource_refs)


def enqueue_accessible_users_version_drop(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> None:
	"""reap a deleted resource's version counter after the delete commits.

	these counters carry no TTL by design - an expiring counter resets to 0 and
	makes an entry invalidated at version N addressable again - so a resource
	that is gone for good would otherwise leave its key behind forever.

	POST-COMMIT, not inline, and that ordering is load-bearing: deleting the
	key resets the resource's version to 0, which is safe only once the row is
	actually gone. dropping it inline and then rolling back would leave a live
	resource whose old cached entries are addressable again.

	a failed drop is a leak, not a correctness fault - the row is gone, so
	every resolve for it returns empty - so unlike an invalidation this one
	does not retry.
	"""

	async def drop_after_commit(db: AsyncSession) -> None:
		_ = db
		if not await cache.delete(
			_accessible_users_version_key(resource_type, resource_id)
		):
			logger.warning(
				"accessible-user version key delete failed for %s %s",
				resource_type.value,
				resource_id,
			)

	enqueue_post_commit_action(session, drop_after_commit)


async def resource_refs_for_subject(
	subject_kind: Literal["user", "group", "role"],
	subject_id: TypeID,
	session: AsyncSession,
) -> list[ResourceRef]:
	"""return resources carrying a rule for one subject.

	descendants are deliberately excluded: their cached answers record these
	resources as ancestors and expire themselves on the next read.
	"""
	subject_col = {
		"user": AccessRule.subject_user_id,
		"group": AccessRule.subject_group_id,
		"role": AccessRule.subject_role_id,
	}[subject_kind]
	fk_cols = [
		(config.rule_fk, resource_type)
		for resource_type, config in RESOURCE_CONFIG.items()
		if is_acl_resource_config(config)
	]
	rows = (
		await session.execute(
			select(*[column for column, _ in fk_cols]).where(subject_col == subject_id)
		)
	).all()
	refs: list[ResourceRef] = []
	for row in rows:
		for value, (_column, resource_type) in zip(row, fk_cols, strict=True):
			if value is not None:
				refs.append((resource_type, TypeID(value)))
	return list(dict.fromkeys(refs))


async def enqueue_accessible_users_invalidation_for_subject(
	subject_kind: Literal["user", "group", "role"],
	subject_id: TypeID,
	session: AsyncSession,
) -> None:
	"""invalidate resources using one subject after the transaction commits."""
	resource_refs = await resource_refs_for_subject(subject_kind, subject_id, session)

	async def invalidate_after_commit(db: AsyncSession) -> None:
		_ = db
		await _invalidate_resource_refs(resource_refs)

	enqueue_post_commit_action(session, invalidate_after_commit)


async def invalidate_accessible_users_for_resource_types(
	resource_types: list[ResourceType],
) -> None:
	"""invalidate whole resource types through bounded generation increments."""
	await _increment_versions_until_written(
		[
			_accessible_users_type_version_key(resource_type)
			for resource_type in affected_resource_types(resource_types)
		],
		"resource types",
	)


async def invalidate_accessible_users_for_role_defaults(
	role_ids: list[TypeID],
	session: AsyncSession,
) -> None:
	"""invalidate resource types affected by role-default access."""
	if not role_ids:
		return
	roles = list(await session.scalars(select(Role).where(Role.id.in_(role_ids))))
	resource_types = [
		resource_type
		for role in roles
		for resource_type in default_access_resource_types(
			role.get_default_permissions().resource_access
		)
	]
	await invalidate_accessible_users_for_resource_types(resource_types)


#: retries before an invalidation write is declared a critical fault. the
#: 24h TTL is only correct because this cache is perfectly invalidated.
_INVALIDATION_ATTEMPTS = 5

#: seconds before the first retry, doubled each attempt: ~1.5s total, short
#: enough for a post-commit drain, long enough to ride out a failover.
_INVALIDATION_BACKOFF_SECONDS = 0.05


async def _increment_versions_until_written(
	keys: list[str],
	described_as: str,
) -> None:
	"""increment version keys, retrying until the write lands.

	this cache is an AUTHORIZATION GATE (`collaborative_documents` joins on it)
	and the fanout audience for resource events, and its entries live for a
	day. the mutation that triggered this has already committed, so a dropped
	increment cannot be rolled back and nothing else retries it - it would
	simply leave revoked principals admitted for the full TTL.

	so this path is not fail-open. it retries with backoff, and exhausting the
	retries is a critical fault to be alerted on, not a warning to move past.
	"""
	if not keys:
		return
	delay = _INVALIDATION_BACKOFF_SECONDS
	for attempt in range(1, _INVALIDATION_ATTEMPTS + 1):
		if await cache.increment_many(keys):
			if attempt > 1:
				logger.warning(
					"accessible-user cache invalidation for %s landed on attempt %d",
					described_as,
					attempt,
				)
			return
		if attempt < _INVALIDATION_ATTEMPTS:
			await asyncio.sleep(delay)
			delay *= 2
	logger.critical(
		"accessible-user cache invalidation for %s FAILED after %d attempts; "
		"revoked access may still be served from cache for up to %d seconds",
		described_as,
		_INVALIDATION_ATTEMPTS,
		settings.cache.accessible_users_ttl_seconds,
		extra={"keys": keys},
	)


async def _invalidate_resource_refs(
	resource_refs: list[ResourceRef],
) -> None:
	"""orphan cached values by incrementing concrete resource versions.

	one transactional pipeline for the whole set rather than one round trip
	per ref: this path receives a whole subject's grant list, which is
	unbounded.
	"""
	await _increment_versions_until_written(
		[
			_accessible_users_version_key(resource_type, resource_id)
			for resource_type, resource_id in resource_refs
		],
		", ".join(
			f"{resource_type.value} {resource_id}"
			for resource_type, resource_id in resource_refs[:10]
		)
		+ (f" (+{len(resource_refs) - 10} more)" if len(resource_refs) > 10 else ""),
	)


async def _resolve_accessible_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel = AccessLevel.READER,
	resolved_user_ids: dict[
		tuple[ResourceType, TypeID, AccessLevel, bool, bool], frozenset[TypeID]
	]
	| None = None,
	resolving_access: set[tuple[ResourceType, TypeID, AccessLevel, bool, bool]]
	| None = None,
	include_operators: bool = True,
	non_transitive_used: bool = False,
	consulted_refs: dict[ResourceRef, int] | None = None,
	traversal_depth: int = 0,
	cycle_truncated: set[tuple[ResourceType, TypeID, AccessLevel, bool, bool]]
	| None = None,
) -> list[TypeID]:
	"""recursively resolve accessible users through the inheritance graph."""
	if resolved_user_ids is None:
		resolved_user_ids = {}
	if resolving_access is None:
		resolving_access = set()
	if cycle_truncated is None:
		cycle_truncated = set()
	if traversal_depth >= MAX_INHERITANCE_DEPTH:
		# `[]` is a truncation, not an answer: the callers folding it in must not
		# be memoised, or a shallower ref would later read the truncated set.
		cycle_truncated.update(resolving_access)
		return []
	await _record_versions([(resource_type, resource_id)], consulted_refs)
	access_key = (
		resource_type,
		resource_id,
		required_level,
		include_operators,
		non_transitive_used,
	)
	if access_key in resolved_user_ids:
		return list(resolved_user_ids[access_key])
	if access_key in resolving_access:
		# cycle break: `[]` is a truncation, not an answer, so no frame folding it
		# in may be memoised.
		cycle_truncated.update(resolving_access)
		return []
	resolving_access.add(access_key)
	config = RESOURCE_CONFIG[resource_type]
	if (
		await session.scalar(select(config.id_col).where(config.id_col == resource_id))
		is None
	):
		resolving_access.remove(access_key)
		resolved_user_ids[access_key] = frozenset()
		return []
	candidate = aliased(User)
	user_ids: set[TypeID] = set()
	if is_acl_resource_config(config):
		direct_access = direct_resource_access_predicate(
			candidate.id,
			resource_type,
			required_level,
		)
		access = (
			resource_operator_predicate(candidate.id, resource_type) | direct_access
			if include_operators
			else direct_access
		)
		stmt = select(candidate.id).where(
			candidate.is_active.is_(True),
			exists(
				select(1)
				.where(
					config.id_col == resource_id,
					access,
				)
				.correlate(candidate)
			),
		)
		user_ids.update(await session.scalars(stmt))
	elif include_operators:
		user_ids.update(
			await session.scalars(
				select(candidate.id).where(
					candidate.is_active.is_(True),
					resource_operator_predicate(candidate.id, resource_type),
				)
			)
		)
	author_id = (
		await session.scalar(
			select(config.author_fk).where(config.id_col == resource_id)
		)
		if config.author_fk is not None
		else None
	)
	parents = await load_parent_resource_refs(resource_type, resource_id, session)
	# one round trip for the whole parent set, before any of their rows are read
	await _record_versions(
		[(parent.parent_type, parent.parent_id) for parent in parents],
		consulted_refs,
	)
	for parent in parents:
		if not parent.transitive and non_transitive_used:
			continue
		for grant in parent.inherited_levels.get(required_level, ()):
			parent_user_ids = await _resolve_accessible_user_ids(
				parent.parent_type,
				parent.parent_id,
				session,
				grant.parent_level,
				resolved_user_ids,
				resolving_access,
				include_operators,
				non_transitive_used or not parent.transitive,
				consulted_refs,
				traversal_depth + 1,
				cycle_truncated,
			)
			if grant.requires_author:
				if author_id is not None and author_id in parent_user_ids:
					user_ids.add(author_id)
			else:
				user_ids.update(parent_user_ids)
	resolving_access.remove(access_key)
	if access_key in cycle_truncated:
		cycle_truncated.discard(access_key)
	else:
		resolved_user_ids[access_key] = frozenset(user_ids)
	return list(user_ids)
