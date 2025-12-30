"""openai-compatible api surface.

this is a thin compatibility layer that maps openai-style requests
into nokodo AI's sdk.

currently implemented:
- post /chat/completions (non-streaming)
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.messages import AssistantMessage, Message, SystemMessage, UserMessage


router = APIRouter(prefix="/openai", tags=["openai"])


class OpenAIChatMessage(BaseModel):
	role: str
	content: str


class OpenAIChatCompletionRequest(BaseModel):
	model: str
	messages: list[OpenAIChatMessage]
	temperature: float | None = None
	max_tokens: int | None = None


class OpenAIChatCompletionResponseMessage(BaseModel):
	role: str = "assistant"
	content: str


class OpenAIChatCompletionChoice(BaseModel):
	index: int = 0
	message: OpenAIChatCompletionResponseMessage
	finish_reason: str | None = "stop"


class OpenAIChatCompletionUsage(BaseModel):
	prompt_tokens: int = 0
	completion_tokens: int = 0
	total_tokens: int = 0


class OpenAIChatCompletionResponse(BaseModel):
	id: str = Field(default="chatcmpl")
	object: str = "chat.completion"
	created: int = Field(default_factory=lambda: int(time.time()))
	model: str
	choices: list[OpenAIChatCompletionChoice]
	usage: OpenAIChatCompletionUsage = Field(default_factory=OpenAIChatCompletionUsage)


@router.post("/chat/completions", response_model=OpenAIChatCompletionResponse)
async def chat_completions(
	req: OpenAIChatCompletionRequest,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> OpenAIChatCompletionResponse:
	# map messages into sdk messages
	sdk_messages: list[Message] = []
	for m in req.messages:
		match m.role:
			case "system":
				sdk_messages.append(SystemMessage.from_text(m.content))
			case "assistant":
				sdk_messages.append(AssistantMessage.from_text(m.content))
			case _:
				sdk_messages.append(UserMessage.from_text(m.content))

	llm = ChatModel(req.model)
	assistant = await llm.generate(
		sdk_messages,
		stream=False,
		temperature=req.temperature,
		max_tokens=req.max_tokens,
	)

	usage = OpenAIChatCompletionUsage()
	if assistant.usage is not None:
		usage.prompt_tokens = assistant.usage.input_tokens
		usage.completion_tokens = assistant.usage.output_tokens
		usage.total_tokens = assistant.usage.total_tokens

	return OpenAIChatCompletionResponse(
		model=req.model,
		choices=[
			OpenAIChatCompletionChoice(
				index=0,
				message=OpenAIChatCompletionResponseMessage(content=assistant.text),
				finish_reason="stop",
			)
		],
		usage=usage,
	)
