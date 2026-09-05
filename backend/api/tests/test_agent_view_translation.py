"""agent-to-agent context view translation coverage."""

import pytest

from api.v1.service.chat.filters.agent_view_translation import (
	AgentViewTranslationFilter,
)
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.messages import UserMessage
from nokodo_ai.threads import Thread


@pytest.mark.asyncio
async def test_agent_view_translation_stub_is_inert() -> None:
	message = UserMessage.from_text("hello")
	state = AgentIterationState(thread=Thread(messages=[message]), tools=[])
	result = await AgentViewTranslationFilter().process(
		state,
		agent_context={},
		app_context=None,
	)
	assert result is state
	assert result.thread.messages == [message]
