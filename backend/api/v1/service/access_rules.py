"""service helpers for access rules."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.permissions import ResourceType
from api.schemas.access_rule import AccessRuleCreate
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	RESOURCE_CONFIG,
	require_resource_access,
	resolve_effective_level,
)
from api.v1.service.vectorize import sync_resource_vector_acl
from nokodo_ai.utils.typeid import TypeID


def _rule_key(rule: AccessRuleCreate) -> str:
	"""generate a unique key for deduplication."""
	if rule.subject_user_id is not None:
		return f"user:{rule.subject_user_id}"
	if rule.subject_group_id is not None:
		return f"group:{rule.subject_group_id}"
	if rule.subject_role_id is not None:
		return f"role:{rule.subject_role_id}"
	return "public"


def _access_rule_key(rule: AccessRule) -> str:
	"""generate a unique key for deduplication from an AccessRule."""
	if rule.subject_user_id is not None:
		return f"user:{rule.subject_user_id}"
	if rule.subject_group_id is not None:
		return f"group:{rule.subject_group_id}"
	if rule.subject_role_id is not None:
		return f"role:{rule.subject_role_id}"
	return "public"


def _apply_resource_fk(
	access_rule: AccessRule,
	resource_type: ResourceType,
	resource_id: TypeID,
) -> None:
	"""set the correct resource FK on an access rule by resource type."""
	match resource_type:
		case ResourceType.THREAD:
			access_rule.thread_id = resource_id
		case ResourceType.PROJECT:
			access_rule.project_id = resource_id
		case ResourceType.AGENT:
			access_rule.agent_id = resource_id
		case ResourceType.NOTE:
			access_rule.note_id = resource_id
		case ResourceType.MEMORY:
			access_rule.memory_id = resource_id
		case ResourceType.TASK:
			access_rule.task_id = resource_id
		case ResourceType.FILE:
			access_rule.file_id = resource_id
		case ResourceType.PLUGIN:
			access_rule.plugin_id = resource_id
		case ResourceType.PROMPT:
			access_rule.prompt_id = resource_id
		case ResourceType.GROUP:
			access_rule.group_id = resource_id
		case ResourceType.REMINDER_LIST:
			access_rule.reminder_list_id = resource_id


async def _list_rules_for_resource(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> list[AccessRule]:
	"""list all access rules for a specific resource, ordered by order_index."""
	config = RESOURCE_CONFIG[resource_type]

	stmt = (
		select(AccessRule)
		.where(config.rule_fk == resource_id)
		.order_by(AccessRule.order_index)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_access_rules_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> list[AccessRule]:
	"""list access rules for a resource without authorization checks.

	the caller is responsible for verifying that the principal has
	appropriate permissions before calling this function.
	"""
	return await _list_rules_for_resource(resource_type, resource_id, session)


async def list_access_rules(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> list[AccessRule]:
	"""list access rules for a resource (requires admin access).

	fetches rules once for both the admin check and the return value,
	avoiding a redundant DB round-trip vs require_resource_access + fetch.
	"""
	config = RESOURCE_CONFIG[resource_type]
	stmt = select(config.id_col)
	if config.owner_fk is not None:
		stmt = select(config.id_col, config.owner_fk)
	stmt = stmt.where(config.id_col == resource_id)

	result = await session.execute(stmt)
	row = result.one_or_none()
	if row is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)

	owner_id: TypeID | None = (
		row[1] if config.owner_fk is not None and len(row) > 1 else None
	)

	rules = await _list_rules_for_resource(resource_type, resource_id, session)

	effective = resolve_effective_level(
		principal,
		resource_type,
		rules,
		owner_id=owner_id,
	)
	if effective != AccessLevel.ADMIN:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)

	return rules


async def set_access_rules(
	resource_type: ResourceType,
	resource_id: TypeID,
	rules: list[AccessRuleCreate],
	session: AsyncSession,
	*,
	principal: Principal,
) -> list[AccessRule]:
	"""
	replace all access rules for a resource.

	requires admin access on the resource.
	subject FK validity is enforced by the database.
	"""
	await require_resource_access(
		resource_id,
		session,
		principal,
		resource_type,
		required_level=AccessLevel.ADMIN,
	)
	return await _set_rules_impl(resource_type, resource_id, rules, session)


async def set_access_rules_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	rules: list[AccessRuleCreate],
	session: AsyncSession,
) -> list[AccessRule]:
	"""replace all access rules for a resource without authorization checks.

	the caller is responsible for verifying that the principal has
	appropriate permissions before calling this function.
	subject FK validity is enforced by the database.
	"""
	return await _set_rules_impl(resource_type, resource_id, rules, session)


async def _set_rules_impl(
	resource_type: ResourceType,
	resource_id: TypeID,
	rules: list[AccessRuleCreate],
	session: AsyncSession,
) -> list[AccessRule]:
	"""shared implementation for replacing access rules on a resource."""
	existing = await _list_rules_for_resource(resource_type, resource_id, session)
	existing_by_key = {_access_rule_key(r): r for r in existing}
	desired_keys: set[str] = set()

	for i, rule in enumerate(rules):
		rule_key = _rule_key(rule)
		if rule_key in desired_keys:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="duplicate subject in access rules",
			)
		desired_keys.add(rule_key)

		access_rule = existing_by_key.get(rule_key)
		if access_rule is None:
			access_rule = AccessRule(
				subject_user_id=rule.subject_user_id,
				subject_group_id=rule.subject_group_id,
				subject_role_id=rule.subject_role_id,
				level=rule.level,
				order_index=rule.order_index if rule.order_index != 0 else i,
				metadata_=rule.metadata,
			)
			_apply_resource_fk(access_rule, resource_type, resource_id)
			session.add(access_rule)
		else:
			access_rule.level = rule.level
			access_rule.order_index = rule.order_index if rule.order_index != 0 else i
			if rule.metadata is not None:
				access_rule.metadata_ = rule.metadata

	# remove rules no longer in the list
	for key, existing_rule in existing_by_key.items():
		if key not in desired_keys:
			await session.delete(existing_rule)

	try:
		await session.commit()
	except IntegrityError:
		await session.rollback()
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="invalid subject reference - user, group, or role not found",
		)

	# sync acl metadata to qdrant (no-op if resource has no chunks)
	await sync_resource_vector_acl(resource_id, resource_type, session)

	return await _list_rules_for_resource(resource_type, resource_id, session)
