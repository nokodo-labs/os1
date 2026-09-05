"""the ``private`` facet boundary: who may read it, and how it is written.

projection belongs in the service, not the router: FastAPI's
``response_model`` cannot carry a serialization context, and payload caches
are not principal-keyed, so they store the full payload.
"""

from fastapi import HTTPException, status

from api.models.mixins import MetadataJSONMixin
from api.permissions import ResourceType
from api.schemas.common import PrivateFacetModel, PrivateInputModel
from api.v1.service.authentication import Principal
from nokodo_ai.types.json import JSONObject
from nokodo_ai.types.sentinels import MISSING, MissingType


def project_private[SchemaT: PrivateFacetModel](
	principal: Principal,
	resource_type: ResourceType,
	payloads: list[SchemaT],
) -> list[SchemaT]:
	"""drop the private facet unless the principal operates the resource.

	pass a one-item list to project a single payload.

	the result is read-only: the copy is shallow (and an operator gets the
	source objects), so mutating a projected payload reaches back into the one
	the caller passed in. finish building a payload before projecting it.
	"""
	if principal.is_resource_operator(resource_type):
		return payloads
	return [payload.model_copy(update={"private": None}) for payload in payloads]


def public_payload[SchemaT: PrivateFacetModel](payload: SchemaT) -> SchemaT:
	"""drop the private facet unconditionally.

	for payloads with no single reader to authorize, such as event fanout and
	SSE frames.
	"""
	return payload.model_copy(update={"private": None})


def require_private_write(
	principal: Principal,
	resource_type: ResourceType,
	private: PrivateInputModel | MissingType,
) -> None:
	"""reject a submitted ``private`` facet from a non-operator.

	raises 403 rather than silently stripping the facet.
	"""
	if not isinstance(private, PrivateInputModel):
		return
	if not principal.is_resource_operator(resource_type):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)


def apply_metadata_write(
	row: MetadataJSONMixin,
	public: JSONObject | MissingType,
	private: PrivateInputModel | MissingType = MISSING,
) -> None:
	"""write the submitted halves of a metadata payload onto a row.

	a half left ``MISSING`` is preserved as-is.
	"""
	private_metadata: JSONObject | MissingType = (
		private.metadata if isinstance(private, PrivateInputModel) else MISSING
	)
	if public is MISSING and private_metadata is MISSING:
		return
	row.set_metadata(public=public, private=private_metadata)
