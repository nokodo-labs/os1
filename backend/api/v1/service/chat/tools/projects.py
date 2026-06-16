"""projects tools - get/search projects."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.models.project import Project
from api.schemas.search import Page
from api.v1.service import projects as project_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


def _project_search_result(project: Project) -> dict[str, object]:
	"""summarize a project for agent search results."""
	return {
		"id": str(project.id),
		"name": project.name,
		**({"description": project.description[:100]} if project.description else {}),
	}


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
		description="hybrid search query for project names and descriptions.",
		min_length=1,
		max_length=500,
	)
	limit: int = Field(
		default=3,
		description="max projects to return when searching",
		ge=1,
		le=20,
	)
	offset: int = Field(
		default=0,
		description="number of search results to skip before this page.",
		ge=0,
	)


class ProjectGetTool(Tool[AppContext]):
	"""fetch a specific project by ID or search projects by query."""

	name: str = Field(default="project_get")
	description: str = Field(
		default=(
			"retrieve projects. provide project_id to get a specific project, "
			"or provide a query to search project names and descriptions by meaning."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ProjectGetInput.model_json_schema()
	)

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		inp = ProjectGetInput.model_validate(kwargs)

		if inp.project_id:
			try:
				project = await project_service.get_project_payload(
					TypeID(inp.project_id),
					__app_context__.session,
					__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __tool_call_context__)
			result: dict[str, object] = {
				"status": "success",
				"message": "project retrieved",
				"id": str(project.id),
				"name": project.name,
			}
			if project.description:
				result["description"] = project.description
			if project.thread_ids:
				result["chat_ids"] = [str(chat_id) for chat_id in project.thread_ids]
			return self.success(json.dumps(result), __tool_call_context__)

		if not inp.query:
			return self.error(
				"provide project_id to fetch a project or query to search",
				__tool_call_context__,
			)

		try:
			scored = await project_service.search_projects(
				inp.query,
				__app_context__.session,
				principal=__app_context__.principal,
				limit=inp.limit + 1,
				offset=inp.offset,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __tool_call_context__)

		page = Page(
			items=[hit.item for hit in scored[: inp.limit]],
			has_more=len(scored) > inp.limit,
		)
		if not page.items:
			out = {
				"status": "success",
				"message": "no projects found",
				"count": 0,
				"results": [],
			}
			return self.success(json.dumps(out), __tool_call_context__)

		results = [_project_search_result(item) for item in page.items]
		count = len(results)
		message = f"found {count} {'project' if count == 1 else 'projects'}"
		next_offset = inp.offset + inp.limit if page.has_more else None
		out = {
			"status": "success",
			"message": message,
			"count": count,
			"results": results,
			"next_offset": next_offset,
		}
		return self.success(json.dumps(out), __tool_call_context__)
