"""projects tools - get/search projects."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.v1.service import projects as project_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class ProjectGetInput(BaseModel):
	"""input schema for project_get tool.

	provide project_id to fetch a specific project, or query to search.
	"""

	model_config = ConfigDict(extra="forbid")

	project_id: str | None = Field(
		default=None,
		description=(
			"ID of a specific project to fetch. when provided, query is ignored."
		),
	)
	query: str | None = Field(
		default=None,
		description="text search query for project names and descriptions.",
	)
	limit: int = Field(
		default=3,
		description="max projects to return when searching",
		ge=1,
		le=20,
	)


class ProjectGetTool(Tool[AppContext]):
	"""fetch a specific project by ID or search projects by query."""

	name: str = Field(default="project_get")
	description: str = Field(
		default=(
			"retrieve projects. provide project_id to get a specific project, "
			"or provide a query to search project names and descriptions."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ProjectGetInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = ProjectGetInput.model_validate(kwargs)

		if inp.project_id:
			try:
				project = await project_service.get_project_payload(
					TypeID(inp.project_id),
					__app_context__.session,
					__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __agent_context__)
			result: dict[str, object] = {
				"status": "success",
				"message": "project retrieved",
				"id": str(project.id),
				"name": project.name,
			}
			if project.description:
				result["description"] = project.description
			if project.thread_ids:
				result["thread_ids"] = [
					str(thread_id) for thread_id in project.thread_ids
				]
			return self.success(json.dumps(result), __agent_context__)

		if not inp.query:
			return self.error(
				"provide project_id to fetch a project or query to search",
				__agent_context__,
			)

		try:
			page = await project_service.search_projects(
				inp.query,
				__app_context__.session,
				principal=__app_context__.principal,
				limit=inp.limit,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __agent_context__)

		if not page.items:
			out = {
				"status": "success",
				"message": "no projects found",
				"count": 0,
				"results": [],
			}
			return self.success(json.dumps(out), __agent_context__)

		results = [
			{
				"id": str(item.id),
				"name": item.title,
				**({"description": item.preview} if item.preview else {}),
			}
			for item in page.items
		]
		count = len(results)
		message = f"found {count} {'project' if count == 1 else 'projects'}"
		out = {
			"status": "success",
			"message": message,
			"count": count,
			"results": results,
		}
		return self.success(json.dumps(out), __agent_context__)
