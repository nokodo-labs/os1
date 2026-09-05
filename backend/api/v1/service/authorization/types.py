"""shared authorization service types."""

from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement

from api.permissions import ResourceType
from api.v1.service.authentication import Principal
from nokodo_ai.utils.typeid import TypeID


type AccessSubject = (
	Principal | ColumnElement[TypeID] | InstrumentedAttribute[TypeID] | TypeID | str
)

type ResourceRef = tuple[ResourceType, TypeID]
