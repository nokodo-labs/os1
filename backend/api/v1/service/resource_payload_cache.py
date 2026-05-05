"""resource-scoped API payload cache helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ValidationError

from api.permissions import ResourceType
from api.redis import cache
from api.settings import settings
from nokodo_ai.utils.typeid import TypeID


def resource_payload_tag(resource_type: ResourceType, resource_id: TypeID) -> str:
	return f"resource-payload:{resource_type.value}:{str(resource_id)}"


def _payload_key(
	resource_type: ResourceType,
	resource_id: TypeID,
	schema_type: type[BaseModel],
	variant: str,
) -> str:
	return ":".join(
		(
			"resource-payload",
			resource_type.value,
			str(resource_id),
			schema_type.__module__,
			schema_type.__qualname__,
			variant,
		)
	)


async def get_cached_resource_payload[SchemaT: BaseModel](
	resource_type: ResourceType,
	resource_id: TypeID,
	schema_type: type[SchemaT],
	variant: str = "default",
) -> SchemaT | None:
	key = _payload_key(resource_type, resource_id, schema_type, variant)
	value = await cache.get(key)
	if not isinstance(value, dict):
		return None
	try:
		return schema_type.model_validate(value)
	except ValidationError:
		await cache.delete(key)
		return None


async def set_cached_resource_payload(
	resource_type: ResourceType,
	resource_id: TypeID,
	payload: BaseModel,
	variant: str = "default",
) -> None:
	await cache.set(
		_payload_key(resource_type, resource_id, type(payload), variant),
		payload.model_dump(mode="json", by_alias=True),
		ttl=settings.cache.resource_payload_ttl_seconds,
		tags=[resource_payload_tag(resource_type, resource_id)],
	)


async def get_or_set_resource_payload_cache[SchemaT: BaseModel](
	resource_type: ResourceType,
	resource_id: TypeID,
	schema_type: type[SchemaT],
	factory: Callable[[], Awaitable[SchemaT]],
	variant: str = "default",
) -> SchemaT:
	cached = await get_cached_resource_payload(
		resource_type,
		resource_id,
		schema_type,
		variant=variant,
	)
	if cached is not None:
		return cached
	payload = await factory()
	await set_cached_resource_payload(
		resource_type,
		resource_id,
		payload,
		variant=variant,
	)
	return payload


async def invalidate_resource_payload_cache(
	resource_type: ResourceType,
	resource_id: TypeID,
) -> None:
	await cache.invalidate_tag(resource_payload_tag(resource_type, resource_id))
