"""resource origin deletion orchestration."""

import logging
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message
from api.permissions import ResourceType
from api.v1.service.authentication import Principal
from api.v1.service.authorization import RESOURCE_CONFIG
from api.v1.service.calendar import delete_calendar, delete_calendar_event
from api.v1.service.files import delete_file
from api.v1.service.notes import delete_note
from api.v1.service.projects import delete_project
from api.v1.service.reminders import delete_reminder, delete_reminder_list
from api.v1.service.resource_origins.tracking import load_originated_resources
from api.v1.service.threads import delete_thread
from api.v1.service.threads.core import (
	execute_thread_deletion,
	prepare_thread_deletion,
)
from api.v1.service.threads.messages import (
	execute_user_message_turn_deletion,
	prepare_user_message_turn_deletion,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

type OriginDeletionHandler = Callable[
	[TypeID, AsyncSession, Principal, str | None, bool],
	Awaitable[None],
]


async def _delete_file(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	permanent: bool,
) -> None:
	await delete_file(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
		permanent=permanent,
	)


async def _delete_note(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	permanent: bool,
) -> None:
	await delete_note(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
		permanent=permanent,
	)


async def _delete_thread(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	permanent: bool,
) -> None:
	await delete_thread(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
		permanent=permanent,
	)


async def _delete_project(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	_permanent: bool,
) -> None:
	await delete_project(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
	)


async def _delete_reminder(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	_permanent: bool,
) -> None:
	await delete_reminder(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
	)


async def _delete_reminder_list(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	_permanent: bool,
) -> None:
	await delete_reminder_list(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
	)


async def _delete_calendar_event(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	_permanent: bool,
) -> None:
	await delete_calendar_event(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
	)


async def _delete_calendar(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None,
	_permanent: bool,
) -> None:
	await delete_calendar(
		resource_id,
		session,
		principal=principal,
		origin_session_id=origin_session_id,
	)


_DELETE_HANDLERS: dict[ResourceType, OriginDeletionHandler] = {
	ResourceType.FILE: _delete_file,
	ResourceType.NOTE: _delete_note,
	ResourceType.THREAD: _delete_thread,
	ResourceType.PROJECT: _delete_project,
	ResourceType.REMINDER: _delete_reminder,
	ResourceType.REMINDER_LIST: _delete_reminder_list,
	ResourceType.CALENDAR_EVENT: _delete_calendar_event,
	ResourceType.CALENDAR: _delete_calendar,
}

_origin_resource_types = {
	resource_type
	for resource_type, config in RESOURCE_CONFIG.items()
	if config.origin_message_fk is not None
}
if set(_DELETE_HANDLERS) != _origin_resource_types:
	missing = sorted(
		resource_type.value
		for resource_type in _origin_resource_types - _DELETE_HANDLERS.keys()
	)
	extra = sorted(
		resource_type.value
		for resource_type in _DELETE_HANDLERS.keys() - _origin_resource_types
	)
	raise RuntimeError(
		f"origin deletion handler mismatch: missing={missing}, extra={extra}"
	)


async def delete_originated_resources(
	resources: list[tuple[ResourceType, TypeID]],
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
	permanent: bool = False,
) -> None:
	"""delete originated resources through their own delete services."""
	for resource_type, resource_id in resources:
		try:
			handler = _DELETE_HANDLERS.get(resource_type)
			if handler is None:
				raise RuntimeError(
					f"{resource_type.value} cannot originate in a message"
				)
			await handler(
				resource_id,
				session,
				principal,
				origin_session_id,
				permanent,
			)
		except HTTPException:
			logger.warning(
				"skipped originated resource deletion",
				extra={
					"resource_type": resource_type.value,
					"resource_id": str(resource_id),
				},
			)


async def delete_thread_with_originated_resources(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
	permanent: bool = False,
) -> None:
	"""delete a thread after deleting resources originated in its messages."""
	prepared = await prepare_thread_deletion(
		thread_id,
		session,
		principal,
		permanent=permanent,
	)
	message_ids = list(
		(
			await session.scalars(
				select(Message.id).where(Message.thread_id == thread_id)
			)
		).all()
	)
	await delete_originated_resources(
		await load_originated_resources(
			[TypeID(str(message_id)) for message_id in message_ids],
			session,
		),
		session,
		principal,
		origin_session_id=origin_session_id,
		permanent=permanent,
	)
	await execute_thread_deletion(
		prepared,
		session,
		origin_session_id=origin_session_id,
	)


async def delete_user_message_turn_with_originated_resources(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a user message turn after deleting its originated resources."""
	prepared = await prepare_user_message_turn_deletion(
		thread_id,
		message_id,
		session,
		principal,
	)
	await delete_originated_resources(
		await load_originated_resources(
			[TypeID(message_id) for message_id in prepared.deleted_ids],
			session,
		),
		session,
		principal,
		origin_session_id=origin_session_id,
	)
	await execute_user_message_turn_deletion(
		prepared,
		session,
		origin_session_id=origin_session_id,
	)
