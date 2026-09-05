"""ACL principal metadata used by vector indexing and search."""

from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_revision import AccessRevision
from api.models.access_rule import AccessLevel, AccessRule
from api.permissions import ResourceType
from api.v1.service.authentication import Principal
from api.v1.service.authorization.config import (
	MAX_INHERITANCE_DEPTH,
	RESOURCE_CONFIG,
	is_acl_resource_config,
)
from api.v1.service.authorization.inheritance import (
	PARENT_LINKS_BY_CHILD,
)
from api.v1.service.vectorstores import VectorChunkResourceType, acl_filter
from nokodo_ai.adapters.base.vectorstores import ChunkFilter
from nokodo_ai.utils.typeid import TypeID


ACL_REVISION_KEY = "acl_revision"


class ACLPrincipalMetadata(TypedDict):
	"""filterable ACL snapshot stored on vector chunks.

	``acl_revision`` aggregates the resource's own access revision with every
	ancestor revision that fed the snapshot, so an ACL change anywhere on the
	inheritance path makes the stamp differ and the staleness sweep repairs it.
	"""

	allowed_user_ids: list[str]
	allowed_group_ids: list[str]
	allowed_role_ids: list[str]
	acl_revision: int


VECTOR_CHUNK_ACCESS_RESOURCE_TYPES: dict[VectorChunkResourceType, ResourceType] = {
	VectorChunkResourceType.THREAD: ResourceType.THREAD,
	VectorChunkResourceType.THREAD_CONTENT: ResourceType.THREAD,
	VectorChunkResourceType.NOTE: ResourceType.NOTE,
	VectorChunkResourceType.MEMORY: ResourceType.MEMORY,
	VectorChunkResourceType.FILE: ResourceType.FILE,
	VectorChunkResourceType.FILE_CONTENT: ResourceType.FILE,
}
ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES: dict[
	ResourceType, tuple[VectorChunkResourceType, ...]
] = {
	ResourceType.THREAD: (
		VectorChunkResourceType.THREAD,
		VectorChunkResourceType.THREAD_CONTENT,
	),
	ResourceType.NOTE: (VectorChunkResourceType.NOTE,),
	ResourceType.MEMORY: (VectorChunkResourceType.MEMORY,),
	ResourceType.FILE: (
		VectorChunkResourceType.FILE,
		VectorChunkResourceType.FILE_CONTENT,
	),
}
VECTOR_CHUNK_PARENT_RESOURCE_TYPES: dict[
	VectorChunkResourceType, VectorChunkResourceType
] = {
	VectorChunkResourceType.FILE_CONTENT: VectorChunkResourceType.FILE,
	VectorChunkResourceType.THREAD_CONTENT: VectorChunkResourceType.THREAD,
}


def _validate_vector_chunk_acl_mappings() -> None:
	for (
		access_resource_type,
		chunk_resource_types,
	) in ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES.items():
		if not is_acl_resource_config(RESOURCE_CONFIG[access_resource_type]):
			raise RuntimeError(
				f"{access_resource_type.value} is not an ACL resource type"
			)
		for chunk_resource_type in chunk_resource_types:
			chunk_access_resource_type = VECTOR_CHUNK_ACCESS_RESOURCE_TYPES[
				chunk_resource_type
			]
			if chunk_access_resource_type != access_resource_type:
				raise RuntimeError(
					f"{chunk_resource_type.value} does not resolve to "
					f"{access_resource_type.value}"
				)
	for (
		chunk_resource_type,
		parent_resource_type,
	) in VECTOR_CHUNK_PARENT_RESOURCE_TYPES.items():
		chunk_access_resource_type = VECTOR_CHUNK_ACCESS_RESOURCE_TYPES[
			chunk_resource_type
		]
		parent_access_resource_type = VECTOR_CHUNK_ACCESS_RESOURCE_TYPES[
			parent_resource_type
		]
		if chunk_access_resource_type != parent_access_resource_type:
			raise RuntimeError(
				f"{chunk_resource_type.value} parent "
				f"{parent_resource_type.value} resolves to a different ACL type"
			)


_validate_vector_chunk_acl_mappings()


def empty_acl_metadata() -> ACLPrincipalMetadata:
	return {
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
		ACL_REVISION_KEY: 0,
	}


def merge_acl_metadata(
	target: ACLPrincipalMetadata,
	source: ACLPrincipalMetadata,
) -> None:
	for key in (
		"allowed_user_ids",
		"allowed_group_ids",
		"allowed_role_ids",
	):
		values = target[key]
		seen = set(values)
		for value in source[key]:
			if value not in seen:
				seen.add(value)
				values.append(value)


async def fetch_bulk_acl_metadata(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, ACLPrincipalMetadata]:
	"""fetch direct and inherited ACL principal metadata for resources."""
	if not resource_ids:
		return {}
	unique_resource_ids = list(dict.fromkeys(resource_ids))
	acl_data = await _fetch_direct_bulk_acl_metadata(
		unique_resource_ids, resource_type, session
	)
	revisions = (
		await session.execute(
			select(AccessRevision.resource_id, AccessRevision.revision).where(
				AccessRevision.resource_type == resource_type,
				AccessRevision.resource_id.in_(unique_resource_ids),
			)
		)
	).all()
	for resource_id, revision in revisions:
		acl_data[str(resource_id)][ACL_REVISION_KEY] = revision
	inherited_acl_data = await _fetch_bulk_inherited_acl_metadata(
		unique_resource_ids,
		resource_type,
		session,
	)
	for resource_id in unique_resource_ids:
		inherited = inherited_acl_data[resource_id]
		merge_acl_metadata(acl_data[resource_id], inherited)
		acl_data[resource_id][ACL_REVISION_KEY] += inherited[ACL_REVISION_KEY]
	return acl_data


async def fetch_bulk_acl_revisions(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, int]:
	"""return the aggregate ACL revision stamped on each resource's chunks."""
	return {
		resource_id: metadata[ACL_REVISION_KEY]
		for resource_id, metadata in (
			await fetch_bulk_acl_metadata(resource_ids, resource_type, session)
		).items()
	}


def vector_acl_filter(
	chunk_resource_types: list[VectorChunkResourceType],
	principal: Principal,
) -> ChunkFilter:
	"""build a vector prefilter from the same ACL graph used by SQL auth."""
	if not chunk_resource_types:
		raise ValueError("chunk_resource_types cannot be empty")
	access_resource_types = {
		VECTOR_CHUNK_ACCESS_RESOURCE_TYPES[resource_type]
		for resource_type in chunk_resource_types
	}
	if len(access_resource_types) != 1:
		raise ValueError(
			"vector_acl_filter chunk_resource_types must share one ACL resource type"
		)
	access_resource_type = next(iter(access_resource_types))
	return acl_filter(
		chunk_resource_types,
		skip_principal_filter=_principal_can_skip_vector_acl(
			access_resource_type, principal
		),
		user_id=str(principal.user.id),
		group_ids=principal.group_ids,
		role_ids=principal.role_ids,
	)


async def _fetch_resource_owner_ids(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, str]:
	config = RESOURCE_CONFIG[resource_type]
	if not is_acl_resource_config(config):
		return {}
	if config.owner_fk is None or not resource_ids:
		return {}
	rows = (
		await session.execute(
			select(config.id_col, config.owner_fk).where(
				config.id_col.in_(resource_ids)
			)
		)
	).all()
	return {
		str(resource_id): str(owner_id)
		for resource_id, owner_id in rows
		if owner_id is not None
	}


async def _fetch_bulk_inherited_acl_metadata(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, ACLPrincipalMetadata]:
	acl_data = {resource_id: empty_acl_metadata() for resource_id in resource_ids}
	ancestors_by_origin: dict[str, set[tuple[ResourceType, str]]] = {
		resource_id: set() for resource_id in resource_ids
	}
	frontier: dict[tuple[ResourceType, bool], dict[str, set[str]]] = {
		(resource_type, False): {
			resource_id: {resource_id} for resource_id in resource_ids
		}
	}
	visited: set[tuple[str, ResourceType, str, bool]] = {
		(resource_id, resource_type, resource_id, False) for resource_id in resource_ids
	}

	# the same bound the SQL predicate and the python resolver walk under: the
	# ancestor set every engine reasons about has to be the same size.
	depth = 0
	while frontier and depth < MAX_INHERITANCE_DEPTH:
		depth += 1
		next_frontier: dict[tuple[ResourceType, bool], dict[str, set[str]]] = {}
		for (
			child_type,
			non_transitive_used,
		), origin_ids_by_child_id in frontier.items():
			child_ids = [TypeID(child_id) for child_id in origin_ids_by_child_id]
			for link in PARENT_LINKS_BY_CHILD[child_type]:
				if not link.transitive and non_transitive_used:
					continue
				if not link.inherited_levels.get(AccessLevel.READER):
					continue
				parent_ids_by_child_id = await link.load_parent_ids_bulk(
					child_ids,
					session,
				)
				origin_ids_by_parent_id: dict[str, set[str]] = {}
				for child_id, parent_ids in parent_ids_by_child_id.items():
					child_origin_ids = origin_ids_by_child_id.get(str(child_id), set())
					for parent_id in parent_ids:
						parent_id_str = str(parent_id)
						for origin_id in child_origin_ids:
							visit_key = (
								origin_id,
								link.parent_type,
								parent_id_str,
								non_transitive_used or not link.transitive,
							)
							if visit_key in visited:
								continue
							visited.add(visit_key)
							origin_ids_by_parent_id.setdefault(
								parent_id_str,
								set(),
							).add(origin_id)
				if not origin_ids_by_parent_id:
					continue
				parent_resource_ids = list(origin_ids_by_parent_id)
				parent_acl_data = await _fetch_direct_bulk_acl_metadata(
					parent_resource_ids,
					link.parent_type,
					session,
				)
				parent_owner_ids = await _fetch_resource_owner_ids(
					parent_resource_ids,
					link.parent_type,
					session,
				)
				for parent_id, origin_ids in origin_ids_by_parent_id.items():
					parent_metadata = empty_acl_metadata()
					owner_id = parent_owner_ids.get(parent_id)
					# A chunk's owner_id covers its own owner; only parent owners
					# flatten here.
					if owner_id is not None:
						parent_metadata["allowed_user_ids"].append(owner_id)
					merge_acl_metadata(
						parent_metadata,
						parent_acl_data.get(parent_id, empty_acl_metadata()),
					)
					for origin_id in origin_ids:
						merge_acl_metadata(acl_data[origin_id], parent_metadata)
						ancestors_by_origin[origin_id].add(
							(link.parent_type, parent_id)
						)
				parent_next_frontier = next_frontier.setdefault(
					(link.parent_type, non_transitive_used or not link.transitive),
					{},
				)
				for parent_id, origin_ids in origin_ids_by_parent_id.items():
					parent_next_frontier.setdefault(parent_id, set()).update(origin_ids)
		frontier = next_frontier

	ancestor_revisions = await _fetch_ancestor_revisions(
		{
			ancestor
			for ancestors in ancestors_by_origin.values()
			for ancestor in ancestors
		},
		session,
	)
	for origin_id, ancestors in ancestors_by_origin.items():
		acl_data[origin_id][ACL_REVISION_KEY] = sum(
			ancestor_revisions.get(ancestor, 0) for ancestor in ancestors
		)

	return acl_data


async def _fetch_ancestor_revisions(
	ancestors: set[tuple[ResourceType, str]],
	session: AsyncSession,
) -> dict[tuple[ResourceType, str], int]:
	"""read the access revision of every ancestor reached by the walk."""
	if not ancestors:
		return {}
	revisions: dict[tuple[ResourceType, str], int] = {}
	ancestor_ids_by_type: dict[ResourceType, list[str]] = {}
	for ancestor_type, ancestor_id in ancestors:
		ancestor_ids_by_type.setdefault(ancestor_type, []).append(ancestor_id)
	for ancestor_type, ancestor_ids in ancestor_ids_by_type.items():
		rows = (
			await session.execute(
				select(AccessRevision.resource_id, AccessRevision.revision).where(
					AccessRevision.resource_type == ancestor_type,
					AccessRevision.resource_id.in_(ancestor_ids),
				)
			)
		).all()
		for resource_id, revision in rows:
			revisions[(ancestor_type, str(resource_id))] = revision
	return revisions


async def _fetch_direct_bulk_acl_metadata(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, ACLPrincipalMetadata]:
	config = RESOURCE_CONFIG[resource_type]
	acl_data = {resource_id: empty_acl_metadata() for resource_id in resource_ids}
	if not is_acl_resource_config(config):
		return acl_data
	stmt = select(
		config.rule_fk,
		AccessRule.subject_user_id,
		AccessRule.subject_group_id,
		AccessRule.subject_role_id,
	).where(config.rule_fk.in_(resource_ids))
	result = await session.execute(stmt)

	for resource_id, user_id, group_id, role_id in result.all():
		resource_id_str = str(resource_id)
		if resource_id_str not in acl_data:
			continue
		if user_id is not None:
			acl_data[resource_id_str]["allowed_user_ids"].append(str(user_id))
		elif group_id is not None:
			acl_data[resource_id_str]["allowed_group_ids"].append(str(group_id))
		elif role_id is not None:
			acl_data[resource_id_str]["allowed_role_ids"].append(str(role_id))

	return acl_data


def _principal_can_skip_vector_acl(
	resource_type: ResourceType,
	principal: Principal,
) -> bool:
	if principal.is_resource_operator(resource_type):
		return True
	return principal.has_default_access(resource_type)
