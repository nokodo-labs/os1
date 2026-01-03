"""chat app context for sdk execution."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID


@dataclass(frozen=True, slots=True)
class AppContext:
	"""application context passed to sdk tools and filters."""

	session: AsyncSession
	principal: Principal
	agent_id: TypeID | None = None

	@property
	def user_id(self) -> TypeID:
		return self.principal.user.id
