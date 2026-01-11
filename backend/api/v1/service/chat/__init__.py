"""chat service package - unified chat runtime operations."""

from api.v1.service.chat.agents import (
	build_agent,
	build_agent_from_orm,
	run_agent,
)
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.models import (
	build_chat_model,
	build_embedding_model,
	resolve_chat_model,
	resolve_embedding_model,
	resolve_model_for_run,
)


__all__ = [
	# models
	"resolve_model_for_run",
	"resolve_chat_model",
	"resolve_embedding_model",
	"build_chat_model",
	"build_embedding_model",
	# agents
	"AppContext",
	"build_agent",
	"build_agent_from_orm",
	"run_agent",
]
