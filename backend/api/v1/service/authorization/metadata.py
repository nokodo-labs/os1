"""ACL principal metadata used by vector indexing and search."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessRule
from api.permissions import ResourceType
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization.config import RESOURCE_CONFIG
from api.v1.service.authorization.inheritance import (
	PARENT_LINKS_BY_CHILD,
	inherited_parent_resource_types,
)
from nokodo_ai.adapters.base.vectorstores import ChunkFilter
from nokodo_ai.utils.typeid import TypeID


type ACLPrincipalMetadata = dict[str, list[str]]


def empty_acl_metadata() -> ACLPrincipalMetadata:
	return {
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
	}


def merge_acl_metadata(
	target: ACLPrincipalMetadata,
	source: ACLPrincipalMetadata,
) -> None:
	for key in ("allowed_user_ids", "allowed_group_ids", "allowed_role_ids"):
		values = target.setdefault(key, [])
		for value in source.get(key, []):
			if value not in values:
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
	inherited_acl_data = await _fetch_bulk_inherited_acl_metadata(
		unique_resource_ids,
		resource_type,
		session,
	)
	for resource_id in unique_resource_ids:
		merge_acl_metadata(
			acl_data[resource_id],
			inherited_acl_data[resource_id],
		)
	return acl_data


async def fetch_acl_metadata(
	resource_id: str,
	resource_type: ResourceType,
	session: AsyncSession,
) -> ACLPrincipalMetadata:
	"""fetch ACL principal metadata for a single resource."""
	bulk = await fetch_bulk_acl_metadata([resource_id], resource_type, session)
	return bulk.get(resource_id, empty_acl_metadata())


def vector_acl_filter(
	resource_type: ResourceType,
	principal: Principal,
) -> ChunkFilter:
	"""build a vector prefilter from the same ACL graph used by SQL auth."""
	return vectorstore_service.acl_filter(
		resource_type.value,
		is_admin=_principal_can_skip_vector_acl(resource_type, principal),
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
	frontier: dict[ResourceType, dict[str, set[str]]] = {
		resource_type: {resource_id: {resource_id} for resource_id in resource_ids}
	}
	visited: set[tuple[str, ResourceType, str]] = {
		(resource_id, resource_type, resource_id) for resource_id in resource_ids
	}

	while frontier:
		next_frontier: dict[ResourceType, dict[str, set[str]]] = {}
		for child_type, origin_ids_by_child_id in frontier.items():
			child_ids = [TypeID(child_id) for child_id in origin_ids_by_child_id]
			for link in PARENT_LINKS_BY_CHILD[child_type]:
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
							visit_key = (origin_id, link.parent_type, parent_id_str)
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
					if owner_id is not None:
						parent_metadata["allowed_user_ids"].append(owner_id)
					merge_acl_metadata(
						parent_metadata,
						parent_acl_data.get(parent_id, empty_acl_metadata()),
					)
					for origin_id in origin_ids:
						merge_acl_metadata(acl_data[origin_id], parent_metadata)
				parent_next_frontier = next_frontier.setdefault(link.parent_type, {})
				for parent_id, origin_ids in origin_ids_by_parent_id.items():
					parent_next_frontier.setdefault(parent_id, set()).update(origin_ids)
		frontier = next_frontier

	return acl_data


async def _fetch_direct_bulk_acl_metadata(
	resource_ids: list[str],
	resource_type: ResourceType,
	session: AsyncSession,
) -> dict[str, ACLPrincipalMetadata]:
	config = RESOURCE_CONFIG[resource_type]
	stmt = select(
		config.rule_fk,
		AccessRule.subject_user_id,
		AccessRule.subject_group_id,
		AccessRule.subject_role_id,
	).where(config.rule_fk.in_(resource_ids))
	result = await session.execute(stmt)

	acl_data = {resource_id: empty_acl_metadata() for resource_id in resource_ids}
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
	if principal.is_admin:
		return True
	if principal.has_default_access(resource_type):
		return True
	return any(
		principal.has_default_access(parent_type)
		for parent_type in inherited_parent_resource_types(resource_type)
	)
