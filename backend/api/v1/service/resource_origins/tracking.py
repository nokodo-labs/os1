"""resource origin assignment and lookup."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.permissions import ResourceType
from api.schemas.message import ResourceAttachment
from api.v1.service.authentication import Principal
from api.v1.service.authorization import RESOURCE_CONFIG, resource_access_predicate
from nokodo_ai.utils.typeid import TypeID


async def assign_resource_origins(
	message_id: TypeID,
	resources: list[ResourceAttachment],
	session: AsyncSession,
	principal: Principal,
) -> list[tuple[ResourceType, TypeID]]:
	"""claim unoriginated resources for a message.

	claiming is what makes a resource eligible for origin cascade deletion, so
	it requires ADMIN on the resource: reader/editor access to someone else's
	resource must never let a caller bind it to their own message.
	"""
	claimed: list[tuple[ResourceType, TypeID]] = []
	seen: set[tuple[ResourceType, str]] = set()
	for resource in resources:
		key = (resource.type, str(resource.id))
		if key in seen:
			continue
		seen.add(key)
		config = RESOURCE_CONFIG[resource.type]
		if config.origin_message_fk is None:
			raise RuntimeError(f"{resource.type.value} cannot originate in a message")
		result = await session.execute(
			update(config.id_col.class_)
			.where(
				config.id_col == resource.id,
				config.origin_message_fk.is_(None),
				resource_access_predicate(
					principal,
					resource.type,
					required_level=AccessLevel.ADMIN,
					include_link_access=True,
				),
			)
			.values({config.origin_message_fk.key: message_id})
			.returning(config.id_col)
		)
		if claimed_id := result.scalar_one_or_none():
			claimed.append((resource.type, TypeID(str(claimed_id))))
	return claimed


async def load_originated_resources(
	message_ids: list[TypeID],
	session: AsyncSession,
) -> list[tuple[ResourceType, TypeID]]:
	"""return resources that originated in the given messages."""
	if not message_ids:
		return []
	message_id_values = [str(message_id) for message_id in message_ids]
	originated: list[tuple[ResourceType, TypeID]] = []
	for resource_type, config in RESOURCE_CONFIG.items():
		if config.origin_message_fk is None:
			continue
		resource_ids = (
			await session.scalars(
				select(config.id_col).where(
					config.origin_message_fk.in_(message_id_values)
				)
			)
		).all()
		originated.extend(
			(resource_type, TypeID(str(resource_id))) for resource_id in resource_ids
		)
	return originated
