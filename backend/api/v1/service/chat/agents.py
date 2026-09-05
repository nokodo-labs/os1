"""agent construction logic."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.access_rule import AccessLevel
from api.models.agent import Agent as AgentORM
from api.models.model import Model
from api.permissions import ResourceType
from api.v1.service.authentication import Principal
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.chat.context import AppContext
from nokodo_ai import Agent as SDKAgent
from nokodo_ai import Filter as SDKFilter
from nokodo_ai import Hook as SDKHook
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.tool import Tool
from nokodo_ai.utils.typeid import TypeID


async def _load_agent(
	agent_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> AgentORM:
	"""load an agent with auth check + model/provider relationships.

	combines access verification and eager loading into a single query
	using the resource access predicate.
	"""
	stmt = (
		select(AgentORM)
		.options(selectinload(AgentORM.model).selectinload(Model.provider))
		.where(
			AgentORM.id == agent_id,
			resource_access_predicate(
				principal,
				ResourceType.AGENT,
				required_level=AccessLevel.READER,
			),
		)
	)
	result = await session.execute(stmt)
	agent = result.scalars().one_or_none()

	if agent is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="agent not found",
		)

	if agent.model is None:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="agent has no model configured",
		)

	return agent


def build_agent(
	chat_model: ChatModel,
	tools: list[Tool[AppContext]] | None = None,
	filters: list[SDKFilter[AppContext]] | None = None,
	hooks: list[SDKHook[AppContext]] | None = None,
	max_iterations: int = 10,
) -> SDKAgent[AppContext]:
	"""build an sdk Agent with the given configuration.

	args:
		chat_model: configured ChatModel for the agent
		tools: list of tools the agent can use
		filters: list of pre-processing filters
		hooks: list of post-execution hooks
		max_iterations: maximum agentic loop iterations

	returns:
		configured SDKAgent ready for execution
	"""
	return SDKAgent[AppContext](
		chat_model=chat_model,
		tools=tools or [],
		filters=filters or [],
		hooks=hooks or [],
		max_iterations=max_iterations,
	)
