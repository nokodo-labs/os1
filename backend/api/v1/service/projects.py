"""project service helpers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.acl import AccessRole
from api.models.project import Project
from api.v1.service.auth import Principal
from api.v1.service.authorization import project_access_predicate
from nokodo_ai.utils.typeid import TypeID


async def load_projects(
	project_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.EDITOR,
) -> list[Project]:
	"""load projects with access control; raise 404 for any missing ids."""
	if not project_ids:
		return []

	stmt = select(Project).where(Project.id.in_(project_ids))
	stmt = stmt.where(project_access_predicate(principal, required_role=required_role))
	result = await session.scalars(stmt)
	projects = list(result.all())
	found = {project.id for project in projects}
	missing = [pid for pid in project_ids if pid not in found]
	if missing:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Projects not found: {missing}",
		)
	return projects
