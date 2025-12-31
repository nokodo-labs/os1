"""Service helpers for threads and messages."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.acl import AccessRole
from api.models.agent import Agent
from api.models.message import (
	AssistantMessage,
	Message,
	MessageType,
	SystemMessage,
	ToolMessage,
	UserMessage,
)
from api.models.project import Project
from api.models.thread import Thread
from api.models.user import User
from api.schemas.message import MessageCreate
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.v1.service import chat_runtime
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	project_access_predicate,
	require_thread_access,
	thread_access_predicate,
)
from api.v1.service.prompt_runtime import render_inline_with_prompts
from nokodo_ai.agent import Agent as SDKAgent
from nokodo_ai.deltas import ChatModelDelta
from nokodo_ai.thread import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


def _ensure_admin_for_hidden(include_hidden: bool, principal: Principal) -> None:
	if include_hidden and not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)


async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
	include_hidden: bool = False,
) -> Thread:
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.where(Thread.id == thread_id)
		.where(
			thread_access_predicate(
				principal,
				required_role=required_role,
				include_hidden=include_hidden,
			)
		)
	)

	if include_hidden:
		stmt = stmt.execution_options(include_deleted=True)
	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def _load_thread_unrestricted(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	include_hidden: bool = False,
) -> Thread:
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.where(Thread.id == thread_id)
	)

	if include_hidden:
		stmt = stmt.execution_options(include_deleted=True)
	else:
		stmt = stmt.where(Thread.deleted_at.is_(None), Thread.is_temporary.is_(False))

	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def _ensure_user(user_id: TypeID, session: AsyncSession) -> None:
	user = await session.get(User, user_id)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found",
		)


async def _load_projects(
	project_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.EDITOR,
) -> list[Project]:
	if not project_ids:
		return []

	stmt = select(Project).where(Project.id.in_(project_ids))
	stmt = stmt.where(project_access_predicate(principal, required_role=required_role))
	result = await session.scalars(stmt)
	projects = list(result.all())
	found = {project.id for project in projects}
	missing = [project_id for project_id in project_ids if project_id not in found]
	if missing:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Projects not found: {missing}",
		)
	return projects


async def create_thread(
	thread_in: ThreadCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Thread:
	owner_id = thread_in.owner_id
	if not principal.is_admin:
		owner_id = TypeID(principal.user.id)
	else:
		await _ensure_user(owner_id, session)

	projects = await _load_projects(thread_in.project_ids, session, principal)
	thread_data = thread_in.model_dump(by_alias=True, exclude={"project_ids"})
	thread_data["owner_id"] = owner_id
	thread = Thread(**thread_data)
	thread.projects = projects
	session.add(thread)
	await session.commit()
	return await _load_thread_unrestricted(
		TypeID(thread.id),
		session,
		include_hidden=True,
	)


async def list_threads(
	session: AsyncSession,
	*,
	principal: Principal,
	owner_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 20,
	include_hidden: bool = False,
) -> list[Thread]:
	_ensure_admin_for_hidden(include_hidden, principal)
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.order_by(Thread.last_activity_at.desc())
		.where(
			thread_access_predicate(
				principal,
				required_role=AccessRole.VIEWER,
				include_hidden=include_hidden,
			)
		)
	)

	if owner_id is not None:
		stmt = stmt.where(Thread.owner_id == owner_id)

	if include_hidden:
		stmt = stmt.execution_options(include_deleted=True)

	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().unique().all())


async def get_thread(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> Thread:
	_ensure_admin_for_hidden(include_hidden, principal)
	return await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
		include_hidden=include_hidden,
	)


async def update_thread(
	thread_id: TypeID,
	thread_in: ThreadUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Thread:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
	)
	update_data = thread_in.model_dump(exclude_unset=True, by_alias=True)
	new_owner_id = update_data.pop("owner_id", None)
	owner_changed = False
	if new_owner_id is not None and new_owner_id != thread.owner_id:
		if not principal.is_admin and thread.owner_id != principal.user.id:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		new_owner = await session.get(User, new_owner_id)
		if not new_owner:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="User not found",
			)
		thread.owner_id = TypeID(new_owner_id)
		thread.owner = new_owner
		owner_changed = True

	project_ids = update_data.pop("project_ids", None)
	for field, value in update_data.items():
		setattr(thread, field, value)

	if project_ids is not None:
		thread.projects = await _load_projects(project_ids, session, principal)

	await session.commit()
	if (
		owner_changed
		and not principal.is_admin
		and str(new_owner_id) != str(principal.user.id)
	):
		return await _load_thread_unrestricted(thread_id, session)

	return await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
	)


async def delete_thread(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
	)

	if not principal.is_admin and thread.owner_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	thread.soft_delete()
	await session.commit()


async def list_messages(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
	include_hidden: bool = False,
) -> list[Message]:
	_ensure_admin_for_hidden(include_hidden, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
		include_hidden=include_hidden,
	)
	stmt = (
		select(Message)
		.where(Message.thread_id == thread_id)
		.order_by(Message.created_at)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_message_tree(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> list[Message]:
	"""Return all messages in a thread as a flat list."""
	_ensure_admin_for_hidden(include_hidden, principal)
	return await list_messages(
		thread_id,
		session,
		principal=principal,
		skip=0,
		limit=10_000,
		include_hidden=include_hidden,
	)


async def get_current_branch(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> list[Message]:
	"""Return the root→leaf path ending at thread.current_message_id."""
	_ensure_admin_for_hidden(include_hidden, principal)
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
		include_hidden=include_hidden,
	)
	if not thread.current_message_id:
		return []

	branch: list[Message] = []
	cur = await session.get(Message, thread.current_message_id)
	while cur is not None:
		branch.insert(0, cur)
		if not cur.parent_id:
			break
		cur = await session.get(Message, cur.parent_id)
	return branch


async def switch_branch(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Thread:
	"""Set current_message_id to the deepest leaf descending from message_id."""
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
	)
	msg = await session.get(Message, message_id)
	if not msg or msg.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Message not found",
		)

	leaf_id: TypeID = message_id
	while True:
		children_stmt = (
			select(Message)
			.where(Message.thread_id == thread_id, Message.parent_id == leaf_id)
			.order_by(Message.created_at)
		)
		children = list((await session.execute(children_stmt)).scalars().all())
		if not children:
			break
		leaf_id = TypeID(children[-1].id)

	thread.current_message_id = leaf_id
	await session.commit()
	return thread


async def create_message(
	thread_id: TypeID,
	message_in: MessageCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Message:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
	)
	data = message_in.model_dump(by_alias=True, exclude={"type"})
	sender_user_id = data.get("sender_user_id")
	if (
		sender_user_id is not None
		and not principal.is_admin
		and str(sender_user_id) != str(principal.user.id)
	):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	if message_in.type == MessageType.USER and sender_user_id is None:
		data["sender_user_id"] = principal.user.id
	parent_id = data.pop("parent_id", None)
	if parent_id is None:
		parent_id = thread.current_message_id
	else:
		parent = await session.get(Message, parent_id)
		if not parent or parent.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Parent message not found",
			)

	match message_in.type:
		case MessageType.USER:
			message = UserMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case MessageType.ASSISTANT:
			message = AssistantMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case MessageType.TOOL:
			message = ToolMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case MessageType.SYSTEM:
			message = SystemMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case _:
			message = UserMessage(thread_id=thread_id, parent_id=parent_id, **data)

	thread.last_activity_at = datetime.now(tz=UTC)
	session.add(message)
	await session.flush()
	thread.current_message_id = message.id
	await session.commit()
	await session.refresh(message)
	return message


async def run_thread(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	agent_id: TypeID | None = None,
	model_id: TypeID | None = None,
	model: str | None = None,
	input: str | None = None,
	temperature: float | None = None,
	max_tokens: int | None = None,
) -> tuple[Message | None, list[Message]]:
	"""run a thread and persist the messages produced by the sdk."""
	user_message: Message | None = None
	if input is not None and input.strip() != "":
		user_message = await create_message(
			thread_id,
			MessageCreate(content=input),
			session,
			principal=principal,
		)

	branch = await get_current_branch(thread_id, session, principal=principal)
	sdk_messages = chat_runtime.build_sdk_messages_from_branch(branch)

	llm = await chat_runtime.resolve_chat_model_for_run(
		session,
		agent_id=agent_id,
		model_id=model_id,
		model=model,
		temperature=temperature,
		max_tokens=max_tokens,
	)

	produced_sdk_messages: list[chat_runtime.SDKMessage] = []
	if agent_id is not None:
		agent = await session.get(Agent, agent_id)
		if agent is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Agent not found",
			)

		# system prompt goes into the thread, not the agent
		if agent.system_prompt:
			rendered_prompt = await render_inline_with_prompts(
				session,
				text=agent.system_prompt,
				variables=None,
			)
			sdk_messages.insert(0, chat_runtime.system_prompt_message(rendered_prompt))

		max_iterations = 10
		cfg = agent.config or {}
		if isinstance(cfg.get("max_iterations"), int):
			max_iterations = int(cfg["max_iterations"])

		sdk_agent = SDKAgent(
			llm=llm,
			tools=[],
			max_iterations=max_iterations,
		)
		sdk_thread = SDKThread(messages=sdk_messages)
		result = await sdk_agent.run(sdk_thread, tool_choice="auto")
		produced_sdk_messages = list(result)  # type: ignore[arg-type]
	else:
		assistant = await llm.generate(sdk_messages, stream=False)
		produced_sdk_messages = [assistant]

	created: list[Message] = []
	for sdk_msg in produced_sdk_messages:
		create_in = chat_runtime.sdk_message_to_orm_create(
			sdk_msg,
			sender_agent_id=agent_id,
		)
		created.append(
			await create_message(
				thread_id,
				create_in,
				session,
				principal=principal,
			)
		)

	return user_message, created


def _sse_event(*, event: str, data: dict[str, object]) -> bytes:
	payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
	return f"event: {event}\ndata: {payload}\n\n".encode()


def _message_to_sse_data(msg: Message) -> dict[str, object]:
	"""serialize a persisted orm message for sse streaming."""
	content_parts: list[dict[str, object]] = []
	for part in msg.content or []:
		if isinstance(part, dict):
			content_parts.append(part)
		else:
			content_parts.append({"type": "text", "text": str(part)})

	return {
		"id": str(msg.id),
		"thread_id": str(msg.thread_id),
		"parent_id": str(msg.parent_id) if msg.parent_id else None,
		"type": msg.type.value if hasattr(msg.type, "value") else str(msg.type),
		"content": content_parts,
		"sender_agent_id": str(msg.sender_agent_id) if msg.sender_agent_id else None,
		"sender_user_id": str(msg.sender_user_id) if msg.sender_user_id else None,
		"created_at": msg.created_at.isoformat() if msg.created_at else None,
	}


async def run_thread_stream(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	agent_id: TypeID | None = None,
	model_id: TypeID | None = None,
	model: str | None = None,
	input: str | None = None,
	temperature: float | None = None,
	max_tokens: int | None = None,
) -> AsyncIterator[bytes]:
	"""stream a thread run as sse events and persist messages as they complete.

	events emitted:
	- message_created: a message was persisted (contains full message data)
	- text_delta: incremental text chunk for the current assistant message
	- error: something went wrong (generic message, never exposes internals)
	- done: stream is complete

	the frontend can render optimistically from these events without refetching.
	"""
	import logging

	logger = logging.getLogger(__name__)

	# persist and stream user message if provided
	if input is not None and input.strip() != "":
		user_msg = await create_message(
			thread_id,
			MessageCreate(content=input),
			session,
			principal=principal,
		)
		yield _sse_event(event="message_created", data=_message_to_sse_data(user_msg))

	branch = await get_current_branch(thread_id, session, principal=principal)
	sdk_messages = chat_runtime.build_sdk_messages_from_branch(branch)

	try:
		llm = await chat_runtime.resolve_chat_model_for_run(
			session,
			agent_id=agent_id,
			model_id=model_id,
			model=model,
			temperature=temperature,
			max_tokens=max_tokens,
		)
	except HTTPException:
		raise
	except Exception:
		logger.exception("failed to resolve chat model")
		yield _sse_event(event="error", data={"message": "failed to initialize model"})
		yield _sse_event(event="done", data={})
		return

	# if we're running as an agent, prepend its system prompt
	if agent_id is not None:
		agent = await session.get(Agent, agent_id)
		if agent is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Agent not found",
			)
		if agent.system_prompt:
			rendered_prompt = await render_inline_with_prompts(
				session,
				text=agent.system_prompt,
				variables=None,
			)
			sdk_messages.insert(0, chat_runtime.system_prompt_message(rendered_prompt))

	# stream chat deltas and persist the final message
	full_text = ""
	try:
		deltas = llm.generate(
			sdk_messages,
			stream=True,
			tools=[],
			tool_choice="auto",
		)
		if not hasattr(deltas, "__aiter__"):
			raise TypeError("expected async iterator for streaming run")
		async for chat_delta in deltas:
			assert isinstance(chat_delta, ChatModelDelta)
			if chat_delta.message.text:
				full_text += chat_delta.message.text
				yield _sse_event(
					event="text_delta",
					data={"text": chat_delta.message.text},
				)
	except Exception:
		logger.exception("error during llm streaming")
		yield _sse_event(event="error", data={"message": "generation failed"})
		yield _sse_event(event="done", data={})
		return

	# persist the final assistant message
	if full_text.strip() != "":
		try:
			assistant_sdk = chat_runtime.SDKAssistantMessage.from_text(full_text)
			create_in = chat_runtime.sdk_message_to_orm_create(
				assistant_sdk,
				sender_agent_id=agent_id,
			)
			assistant_msg = await create_message(
				thread_id,
				create_in,
				session,
				principal=principal,
			)
			yield _sse_event(
				event="message_created", data=_message_to_sse_data(assistant_msg)
			)
		except Exception:
			logger.exception("error persisting assistant message")
			yield _sse_event(event="error", data={"message": "failed to save response"})
			yield _sse_event(event="done", data={})
			return

	yield _sse_event(event="done", data={})
