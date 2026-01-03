"""chat service package - unified chat runtime operations."""

from api.v1.service.chat.agents import (
	RunResult,
	build_agent,
	build_agent_from_orm,
	run_agent,
	run_agent_stream,
	run_thread,
	run_thread_stream,
)
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.converters import (
	sdk_message_to_orm_create,
	system_prompt_message,
)
from api.v1.service.chat.models import (
	build_chat_model,
	build_embedding_model,
	resolve_chat_model_for_run,
	resolve_embedding_model,
	resolve_model_for_run,
)


__all__ = [
	# models
	"resolve_model_for_run",
	"resolve_chat_model_for_run",
	"resolve_embedding_model",
	"build_chat_model",
	"build_embedding_model",
	# agents
	"AppContext",
	"build_agent",
	"build_agent_from_orm",
	"run_agent",
	"run_agent_stream",
	# converters
	"sdk_message_to_orm_create",
	"system_prompt_message",
	# runner (high-level thread execution)
	"RunResult",
	"run_thread",
	"run_thread_stream",
]
