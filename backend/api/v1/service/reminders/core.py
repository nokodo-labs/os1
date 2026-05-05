"""reminder CRUD and occurrence service helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.reminder import (
	Reminder,
	ReminderList,
	ReminderOverride,
	ReminderStatus,
)
from api.permissions import ResourceType
from api.schemas.reminder import Reminder as ReminderOut
from api.schemas.reminder import (
	ReminderCreate,
	ReminderListItemFilters,
	ReminderUpdate,
	ReminderWithSubtasks,
	ScheduledReminderListFilters,
)
from api.schemas.scheduled_item import ReminderSeriesEdit, ScheduledItem
from api.settings import settings
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.reminders.cache import (
	get_cached_reminder_items,
	invalidate_reminder_scheduled_items,
	set_cached_reminder_items,
)
from api.v1.service.reminders.lists import (
	get_or_create_default_reminder_list,
	get_reminder_list,
)
from api.v1.service.reminders.search import REMINDER_SPEC
from api.v1.service.scheduling.recurrence import (
	expand_occurrence_starts,
	occurrence_exists,
	recurrence_after_split,
	recurrence_to_storage,
)
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.vectorize import remove_vectorized_resource, vectorize_resource
from api.v1.tasks.reminders import (
	cancel_reminder_notifications,
	schedule_reminder_notifications,
)
from nokodo_ai.utils.typeid import TypeID


_REMINDER_SORT_COLUMNS = {
	"position": Reminder.position,
	"due_at": Reminder.due_at,
	"remind_at": Reminder.remind_at,
	"title": Reminder.title,
	"created_at": Reminder.created_at,
	"updated_at": Reminder.updated_at,
}


def _max_hierarchy_depth() -> int:
	return settings.limits.max_reminder_hierarchy_depth


async def _invalidate_reminders(
	reminder_ids: list[TypeID] | tuple[TypeID, ...],
) -> None:
	for reminder_id in reminder_ids:
		await invalidate_reminder_scheduled_items(reminder_id)


def _hierarchy_limit_error() -> HTTPException:
	return HTTPException(
		status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
		detail=(f"reminder hierarchy exceeds {_max_hierarchy_depth()} levels"),
	)


def _hierarchy_cycle_error() -> HTTPException:
	return HTTPException(
		status_code=status.HTTP_409_CONFLICT,
		detail="reminder hierarchy contains a cycle",
	)


async def _load_reminder_parent_chain(
	parent: Reminder,
	session: AsyncSession,
) -> list[Reminder]:
	chain: list[Reminder] = []
	seen: set[TypeID] = set()
	current: Reminder | None = parent
	while current is not None:
		current_id = TypeID(current.id)
		if current_id in seen:
			raise _hierarchy_cycle_error()
		seen.add(current_id)
		chain.append(current)
		if len(chain) > _max_hierarchy_depth():
			raise _hierarchy_limit_error()
		if current.parent_id is None:
			break
		current = await session.get(Reminder, current.parent_id)
		if current is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="parent reminder chain is invalid",
			)
	return chain


async def _reminder_subtree_depth(
	reminder_id: TypeID,
	session: AsyncSession,
) -> int:
	depth = 0
	frontier = {reminder_id}
	seen = {reminder_id}
	while frontier:
		result = await session.execute(
			select(Reminder.id).where(Reminder.parent_id.in_(frontier))
		)
		children = {TypeID(row[0]) for row in result.all()}
		if children & seen:
			raise _hierarchy_cycle_error()
		if not children:
			return depth
		depth += 1
		if depth > _max_hierarchy_depth():
			raise _hierarchy_limit_error()
		seen.update(children)
		frontier = children
	return depth


async def _validate_reminder_parent_assignment(
	parent_id: TypeID,
	target_list_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	reminder: Reminder | None = None,
	parent: Reminder | None = None,
) -> Reminder:
	if reminder is not None and parent_id == reminder.id:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="reminder cannot be its own parent",
		)
	parent = parent or await get_reminder(parent_id, session, principal=principal)
	if parent.list_id != target_list_id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="subtask must belong to same list as parent",
		)
	parent_chain = await _load_reminder_parent_chain(parent, session)
	if reminder is not None and any(
		ancestor.id == reminder.id for ancestor in parent_chain
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="reminder cannot be parented to its own descendant",
		)
	subtree_depth = (
		await _reminder_subtree_depth(reminder.id, session)
		if reminder is not None
		else 0
	)
	if len(parent_chain) + subtree_depth > _max_hierarchy_depth():
		raise _hierarchy_limit_error()
	return parent


async def create_reminder(
	data: ReminderCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Reminder:
	"""create a new reminder."""
	target_list_id = data.list_id
	parent: Reminder | None = None
	if data.parent_id:
		parent = await get_reminder(data.parent_id, session, principal=principal)
		if target_list_id and target_list_id != parent.list_id:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="subtask must belong to same list as parent",
			)
		target_list_id = parent.list_id
	if target_list_id is None:
		target_list_id = (
			await get_or_create_default_reminder_list(session, principal)
		).id
	else:
		await get_reminder_list(target_list_id, session, principal=principal)
	if data.parent_id:
		await _validate_reminder_parent_assignment(
			data.parent_id,
			target_list_id,
			session,
			principal,
			parent=parent,
		)
	create_data = data.model_dump(
		exclude_unset=True,
		by_alias=True,
		exclude={"recurrence", "list_id"},
	)
	create_data["list_id"] = target_list_id
	create_data["recurrence"] = recurrence_to_storage(data.recurrence)
	reminder = Reminder(
		owner_id=principal.user_id,
		**create_data,
	)
	session.add(reminder)
	await session.flush()
	await session.refresh(reminder)

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_CREATED,
		data=ReminderOut.model_validate(reminder).model_dump(mode="json"),
		user_id=principal.user_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	await vectorize_resource(spec=REMINDER_SPEC, resource=reminder, session=session)
	await schedule_reminder_notifications(reminder.id, session=session)

	return reminder


async def list_reminders(
	session: AsyncSession,
	principal: Principal,
	list_id: TypeID,
	filters: ReminderListItemFilters | None = None,
	include_subtasks: bool = False,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "position",
	sort_dir: SortDir = "asc",
) -> list[ReminderWithSubtasks]:
	"""list top-level reminders, optionally with subtasks eagerly loaded."""
	reminder_filters = filters or ReminderListItemFilters()
	stmt = select(Reminder).where(Reminder.parent_id.is_(None))

	if include_subtasks:
		stmt = stmt.options(selectinload(Reminder.subtasks))

	await get_reminder_list(list_id, session, principal=principal)
	stmt = stmt.where(Reminder.list_id == list_id)

	if reminder_filters.status_filter is not None:
		stmt = stmt.where(Reminder.status == reminder_filters.status_filter)

	stmt = apply_sort(
		stmt, sort_by=sort_by, sort_dir=sort_dir, columns=_REMINDER_SORT_COLUMNS
	)
	stmt = stmt.offset(skip).limit(limit)

	result = await session.execute(stmt)
	return [ReminderWithSubtasks.model_validate(r) for r in result.scalars().all()]


async def list_scheduled_reminders(
	session: AsyncSession,
	principal: Principal,
	filters: ScheduledReminderListFilters | None = None,
	include_subtasks: bool = False,
	skip: int = 0,
	limit: int = 500,
) -> list[ReminderWithSubtasks]:
	"""list scheduled reminders across accessible reminder lists."""
	reminder_filters = filters or ScheduledReminderListFilters()
	accessible_list_ids = select(ReminderList.id).where(
		resource_access_predicate(principal, ResourceType.REMINDER_LIST),
	)
	stmt = select(Reminder).where(
		or_(Reminder.due_at.is_not(None), Reminder.remind_at.is_not(None)),
		Reminder.list_id.in_(accessible_list_ids),
	)

	if include_subtasks:
		stmt = stmt.options(selectinload(Reminder.subtasks))

	if reminder_filters.status_filter is not None:
		stmt = stmt.where(Reminder.status == reminder_filters.status_filter)

	scheduled_at = func.coalesce(Reminder.due_at, Reminder.remind_at)
	stmt = (
		stmt.order_by(scheduled_at.asc(), Reminder.position.asc())
		.offset(skip)
		.limit(limit)
	)

	result = await session.execute(stmt)
	return [ReminderWithSubtasks.model_validate(r) for r in result.scalars().all()]


async def list_reminder_scheduled_items(
	session: AsyncSession,
	principal: Principal,
	start_at: datetime,
	end_at: datetime,
	include_completed: bool = False,
) -> list[ScheduledItem]:
	"""list reminder-owned scheduled item occurrences."""
	reminder_rows = await _load_reminder_scheduled_rows(
		session,
		principal,
		start_at,
		end_at,
	)
	overrides = await _load_reminder_overrides(
		session,
		[reminder.id for reminder, _reminder_list in reminder_rows],
	)
	items: list[ScheduledItem] = []
	for reminder, reminder_list in reminder_rows:
		cached_items = await get_cached_reminder_items(
			reminder.id,
			start_at,
			end_at,
			include_completed,
		)
		if cached_items is not None:
			items.extend(cached_items)
			continue
		reminder_items = _expand_reminder_scheduled_item(
			reminder,
			reminder_list,
			overrides,
			start_at,
			end_at,
			include_completed=include_completed,
		)
		await set_cached_reminder_items(
			reminder.id,
			reminder_list.id,
			start_at,
			end_at,
			include_completed,
			reminder_items,
		)
		items.extend(reminder_items)
	return items


async def _load_reminder_scheduled_rows(
	session: AsyncSession,
	principal: Principal,
	start_at: datetime,
	end_at: datetime,
) -> list[tuple[Reminder, ReminderList]]:
	scheduled_at = func.coalesce(Reminder.due_at, Reminder.remind_at)
	stmt = (
		select(Reminder, ReminderList)
		.join(ReminderList, Reminder.list_id == ReminderList.id)
		.where(
			scheduled_at.is_not(None),
			scheduled_at <= end_at,
			or_(Reminder.recurrence.is_not(None), scheduled_at >= start_at),
			or_(
				Reminder.recurrence_until.is_(None),
				Reminder.recurrence_until >= start_at,
			),
			resource_access_predicate(
				principal,
				ResourceType.REMINDER_LIST,
			),
		)
	)
	result = await session.execute(stmt)
	return [(row[0], row[1]) for row in result.all()]


async def _load_reminder_overrides(
	session: AsyncSession,
	reminder_ids: list[TypeID],
) -> dict[tuple[TypeID, datetime], ReminderOverride]:
	if not reminder_ids:
		return {}
	result = await session.execute(
		select(ReminderOverride).where(
			ReminderOverride.reminder_id.in_(reminder_ids),
		)
	)
	return {
		(override.reminder_id, override.original_occurrence_at): override
		for override in result.scalars().all()
	}


def _expand_reminder_scheduled_item(
	reminder: Reminder,
	reminder_list: ReminderList,
	overrides: dict[tuple[TypeID, datetime], ReminderOverride],
	start_at: datetime,
	end_at: datetime,
	include_completed: bool,
) -> list[ScheduledItem]:
	anchor = reminder.due_at or reminder.remind_at
	if anchor is None:
		return []
	if reminder.status == ReminderStatus.COMPLETED and not include_completed:
		return []
	expansion_end = _bounded_window_end(end_at, reminder.recurrence_until)
	if expansion_end < start_at:
		return []
	occurrences = expand_occurrence_starts(
		anchor,
		reminder.recurrence,
		start_at,
		expansion_end,
	)
	items: list[ScheduledItem] = []
	for original_start in occurrences:
		override = overrides.get((reminder.id, original_start))
		if override and not include_completed:
			continue
		if original_start < start_at or original_start > end_at:
			continue
		status_value = _reminder_item_status(reminder, override)
		items.append(
			ScheduledItem(
				kind="reminder",
				id=_occurrence_id(reminder.id, original_start),
				parent_id=reminder.id,
				container_id=reminder_list.id,
				reminder_list_id=reminder_list.id,
				original_occurrence_at=original_start,
				effective_start_at=original_start,
				effective_end_at=None,
				all_day=False,
				title=reminder.title,
				description=reminder.description,
				color=reminder_list.color,
				status=status_value,
				readonly=True,
				completed_at=override.completed_at
				if override
				else reminder.completed_at,
			)
		)
	return items


async def get_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	with_subtasks: bool = False,
) -> Reminder:
	"""get a reminder by id."""
	if with_subtasks:
		stmt = (
			select(Reminder)
			.options(selectinload(Reminder.subtasks))
			.where(Reminder.id == reminder_id)
		)
		result = await session.execute(stmt)
		reminder = result.scalars().first()
	else:
		result = await session.execute(
			select(Reminder).where(Reminder.id == reminder_id)
		)
		reminder = result.scalar_one_or_none()

	if not reminder:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reminder not found",
		)
	if reminder.owner_id != principal.user_id and not principal.is_admin:
		await get_reminder_list(reminder.list_id, session, principal=principal)
	return reminder


async def update_reminder(
	reminder_id: TypeID,
	data: ReminderUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Reminder:
	"""update a reminder."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	update_data = data.model_dump(exclude_unset=True, by_alias=True)
	previous_list_id = reminder.list_id
	target_list_id: TypeID | None = None
	moved_descendants: list[Reminder] = []
	if "recurrence" in data.model_fields_set:
		update_data["recurrence"] = recurrence_to_storage(data.recurrence)

	if "status" in update_data and data.status is not None:
		if (
			data.status == ReminderStatus.COMPLETED
			and reminder.status != ReminderStatus.COMPLETED
		):
			update_data["completed_at"] = datetime.now(UTC)
		elif data.status == ReminderStatus.PENDING:
			update_data["completed_at"] = None

	if "list_id" in update_data:
		if data.list_id is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail="list id is required",
			)
		target_list_id = data.list_id
		await get_reminder_list(target_list_id, session, principal=principal)
	next_list_id = target_list_id or reminder.list_id
	if "parent_id" in update_data and data.parent_id is not None:
		await _validate_reminder_parent_assignment(
			data.parent_id,
			next_list_id,
			session,
			principal,
			reminder=reminder,
		)
	elif target_list_id is not None and reminder.parent_id is not None:
		parent = await get_reminder(reminder.parent_id, session, principal=principal)
		if parent.list_id != target_list_id:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="subtask must belong to same list as parent",
			)
	if target_list_id is not None and target_list_id != previous_list_id:
		moved_descendants = await _load_reminder_descendants(reminder.id, session)

	if "title" in update_data:
		if data.title is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail="title is required",
			)
		reminder.title = data.title
	if "description" in update_data:
		reminder.description = data.description
	if "due_at" in update_data:
		reminder.due_at = data.due_at
	if "remind_at" in update_data:
		reminder.remind_at = data.remind_at
	if "recurrence" in update_data:
		reminder.recurrence = update_data["recurrence"]
	if "status" in update_data:
		if data.status is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail="status is required",
			)
		reminder.status = data.status
	if "completed_at" in update_data:
		reminder.completed_at = update_data["completed_at"]
	if target_list_id is not None:
		reminder.list_id = target_list_id
		for descendant in moved_descendants:
			descendant.list_id = target_list_id
	if "parent_id" in update_data:
		reminder.parent_id = data.parent_id
	if "position" in update_data and data.position is not None:
		reminder.position = data.position
	if "metadata_" in update_data and data.metadata is not None:
		reminder.metadata_ = data.metadata

	await session.flush()
	await session.refresh(reminder)

	event_data = data.model_dump(mode="json", exclude_unset=True)
	event_data["id"] = str(reminder.id)
	event_data["updated_at"] = reminder.updated_at.isoformat()
	if "status" in update_data:
		event_data["status"] = reminder.status.value
		event_data["completed_at"] = (
			reminder.completed_at.isoformat() if reminder.completed_at else None
		)
	event_data["previous_list_id"] = str(previous_list_id) if previous_list_id else None
	event_data["list_id"] = str(reminder.list_id)
	if moved_descendants:
		event_data["moved_descendant_ids"] = [
			str(descendant.id) for descendant in moved_descendants
		]
	reminder_ids_to_invalidate = [
		reminder.id,
		*[descendant.id for descendant in moved_descendants],
	]
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_UPDATED,
		data=event_data,
		user_id=principal.user_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await _invalidate_reminders(reminder_ids_to_invalidate)

	if await REMINDER_SPEC.should_revectorize(reminder, data, session):
		await vectorize_resource(spec=REMINDER_SPEC, resource=reminder, session=session)
		for descendant in moved_descendants:
			await vectorize_resource(
				spec=REMINDER_SPEC,
				resource=descendant,
				session=session,
			)
	await schedule_reminder_notifications(reminder.id, session=session)

	return reminder


async def complete_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	cascade: bool = False,
	origin_session_id: str | None = None,
) -> Reminder:
	"""mark a reminder as completed, optionally cascading to subtasks."""
	reminder = await get_reminder(
		reminder_id, session, principal=principal, with_subtasks=cascade
	)
	if reminder.recurrence is not None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="complete a recurring reminder occurrence instead",
		)
	now = datetime.now(UTC)

	reminder.status = ReminderStatus.COMPLETED
	reminder.completed_at = now

	if cascade and reminder.subtasks:
		for subtask in reminder.subtasks:
			if subtask.status != ReminderStatus.COMPLETED:
				subtask.status = ReminderStatus.COMPLETED
				subtask.completed_at = now

	await session.flush()
	await session.refresh(reminder)

	completed_at_value = reminder.completed_at
	completed_at = (
		completed_at_value.isoformat() if completed_at_value is not None else None
	)
	event_data = {
		"id": str(reminder.id),
		"list_id": str(reminder.list_id),
		"status": reminder.status.value,
		"completed_at": completed_at,
		"updated_at": reminder.updated_at.isoformat(),
		"cascade": cascade,
	}
	reminder_ids_to_invalidate = (
		[
			reminder.id,
			*[subtask.id for subtask in reminder.subtasks],
		]
		if cascade
		else [reminder.id]
	)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_COMPLETED,
		data=event_data,
		user_id=principal.user_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await _invalidate_reminders(reminder_ids_to_invalidate)
	for completed_reminder in (
		[reminder, *reminder.subtasks] if cascade else [reminder]
	):
		await vectorize_resource(
			spec=REMINDER_SPEC,
			resource=completed_reminder,
			session=session,
		)
	for completed_reminder_id in reminder_ids_to_invalidate:
		await cancel_reminder_notifications(completed_reminder_id)

	return reminder


async def complete_reminder_occurrence(
	reminder_id: TypeID,
	original_occurrence_at: datetime,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ScheduledItem:
	"""complete a single recurring reminder occurrence."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	anchor = reminder.due_at or reminder.remind_at
	if reminder.recurrence is None or anchor is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="reminder is not recurring",
		)
	if not occurrence_exists(anchor, reminder.recurrence, original_occurrence_at):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="occurrence does not belong to reminder recurrence",
		)
	now = datetime.now(UTC)
	override = await session.get(
		ReminderOverride,
		(reminder.id, original_occurrence_at),
	)
	if override is None:
		override = ReminderOverride(
			reminder_id=reminder.id,
			original_occurrence_at=original_occurrence_at,
			completed_at=now,
		)
		session.add(override)
	else:
		override.completed_at = now
	await session.flush()
	await _publish_reminder_occurrence_completed(
		session,
		reminder,
		override,
		origin_session_id,
	)
	await _invalidate_reminders([reminder.id])
	await schedule_reminder_notifications(reminder.id, session=session)
	reminder_list = await get_reminder_list(
		reminder.list_id,
		session,
		principal=principal,
	)
	return _reminder_occurrence_item(
		reminder,
		original_occurrence_at,
		original_occurrence_at,
		color=reminder_list.color,
		status_value=ReminderStatus.COMPLETED,
		completed_at=override.completed_at,
	)


async def edit_reminder_series(
	reminder_id: TypeID,
	data: ReminderSeriesEdit,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Reminder:
	"""split a recurring reminder and edit this/following occurrences."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	_validate_reminder_series_split(reminder, data.original_occurrence_at)
	new_reminder = _build_reminder_split(reminder, data)
	reminder.recurrence_until = _split_cutoff(data.original_occurrence_at)
	session.add(new_reminder)
	await session.flush()
	await _move_reminder_overrides_after_split(
		session,
		from_reminder=reminder,
		to_reminder=new_reminder,
		split_at=data.original_occurrence_at,
		keep_future=bool(new_reminder.recurrence),
	)
	await session.refresh(reminder)
	await session.refresh(new_reminder)
	await _publish_reminder_series_updated(
		session,
		reminder,
		origin_session_id,
	)
	await _publish_reminder_created(
		session,
		new_reminder,
		origin_session_id,
	)
	await _invalidate_reminders([reminder.id])
	await vectorize_resource(spec=REMINDER_SPEC, resource=reminder, session=session)
	await vectorize_resource(spec=REMINDER_SPEC, resource=new_reminder, session=session)
	await schedule_reminder_notifications(reminder.id, session=session)
	await schedule_reminder_notifications(new_reminder.id, session=session)
	return new_reminder


def _validate_reminder_series_split(
	reminder: Reminder,
	original_occurrence_at: datetime,
) -> None:
	anchor = _reminder_anchor(reminder)
	if reminder.recurrence is None or anchor is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="reminder is not recurring",
		)
	if _after_recurrence_until(reminder.recurrence_until, original_occurrence_at):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="occurrence does not belong to reminder recurrence",
		)
	if not occurrence_exists(anchor, reminder.recurrence, original_occurrence_at):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="occurrence does not belong to reminder recurrence",
		)


def _reminder_anchor(reminder: Reminder) -> datetime | None:
	return reminder.due_at or reminder.remind_at


def _bounded_window_end(
	window_end: datetime, recurrence_until: datetime | None
) -> datetime:
	if recurrence_until is None or recurrence_until > window_end:
		return window_end
	return recurrence_until


def _reminder_item_status(
	reminder: Reminder,
	override: ReminderOverride | None,
) -> ReminderStatus:
	if override is None:
		return reminder.status
	return ReminderStatus.COMPLETED


def _after_recurrence_until(
	recurrence_until: datetime | None,
	original_occurrence_at: datetime,
) -> bool:
	return recurrence_until is not None and original_occurrence_at > recurrence_until


def _split_cutoff(original_occurrence_at: datetime) -> datetime:
	return original_occurrence_at - timedelta(microseconds=1)


def _build_reminder_split(
	reminder: Reminder,
	data: ReminderSeriesEdit,
) -> Reminder:
	changed = data.model_fields_set
	new_due_at, new_remind_at = _split_reminder_times(reminder, data)
	new_recurrence = (
		recurrence_to_storage(data.recurrence)
		if "recurrence" in changed
		else recurrence_to_storage(
			recurrence_after_split(
				_reminder_anchor(reminder) or data.original_occurrence_at,
				reminder.recurrence,
				data.original_occurrence_at,
			)
		)
	)
	if new_recurrence is not None and new_due_at is None and new_remind_at is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="recurring reminder requires due_at or remind_at",
		)
	return Reminder(
		owner_id=reminder.owner_id,
		list_id=reminder.list_id,
		parent_id=reminder.parent_id,
		source_thread_id=reminder.source_thread_id,
		title=data.title if data.title is not None else reminder.title,
		description=data.description
		if "description" in changed
		else reminder.description,
		due_at=new_due_at,
		remind_at=new_remind_at,
		recurrence=new_recurrence,
		recurrence_until=None,
		series_origin_id=reminder.series_origin_id or reminder.id,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=data.position if data.position is not None else reminder.position,
		metadata_=dict(reminder.metadata_ or {}),
	)


def _split_reminder_times(
	reminder: Reminder,
	data: ReminderSeriesEdit,
) -> tuple[datetime | None, datetime | None]:
	changed = data.model_fields_set
	if "due_at" in changed:
		new_due_at = data.due_at
	elif reminder.due_at is not None:
		new_due_at = data.original_occurrence_at
	else:
		new_due_at = None

	if "remind_at" in changed:
		new_remind_at = data.remind_at
	elif reminder.remind_at is not None and reminder.due_at is not None:
		new_remind_at = data.original_occurrence_at + (
			reminder.remind_at - reminder.due_at
		)
	elif reminder.remind_at is not None:
		new_remind_at = data.original_occurrence_at
	else:
		new_remind_at = None
	return new_due_at, new_remind_at


async def _move_reminder_overrides_after_split(
	session: AsyncSession,
	from_reminder: Reminder,
	to_reminder: Reminder,
	split_at: datetime,
	keep_future: bool,
) -> None:
	result = await session.execute(
		select(ReminderOverride).where(
			ReminderOverride.reminder_id == from_reminder.id,
			ReminderOverride.original_occurrence_at >= split_at,
		)
	)
	for override in result.scalars().all():
		if keep_future:
			session.add(
				ReminderOverride(
					reminder_id=to_reminder.id,
					original_occurrence_at=override.original_occurrence_at,
					completed_at=override.completed_at,
				)
			)
		await session.delete(override)


async def _publish_reminder_created(
	session: AsyncSession,
	reminder: Reminder,
	origin_session_id: str | None,
) -> None:
	event = Event(
		scope=EventScope.USER,
		scope_id=reminder.owner_id,
		type=EventType.REMINDER_CREATED,
		data=ReminderOut.model_validate(reminder).model_dump(mode="json"),
		user_id=reminder.owner_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)


async def _publish_reminder_series_updated(
	session: AsyncSession,
	reminder: Reminder,
	origin_session_id: str | None,
) -> None:
	event = Event(
		scope=EventScope.USER,
		scope_id=reminder.owner_id,
		type=EventType.REMINDER_UPDATED,
		data={
			"id": str(reminder.id),
			"list_id": str(reminder.list_id),
			"recurrence_until": reminder.recurrence_until.isoformat()
			if reminder.recurrence_until
			else None,
			"updated_at": reminder.updated_at.isoformat(),
		},
		user_id=reminder.owner_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)


async def _publish_reminder_occurrence_completed(
	session: AsyncSession,
	reminder: Reminder,
	override: ReminderOverride,
	origin_session_id: str | None,
) -> None:
	event_data = {
		"id": str(reminder.id),
		"list_id": str(reminder.list_id),
		"occurrence_id": _occurrence_id(
			reminder.id,
			override.original_occurrence_at,
		),
		"original_occurrence_at": override.original_occurrence_at.isoformat(),
		"status": ReminderStatus.COMPLETED.value,
		"completed_at": override.completed_at.isoformat()
		if override.completed_at
		else None,
	}
	event = Event(
		scope=EventScope.USER,
		scope_id=reminder.owner_id,
		type=EventType.REMINDER_COMPLETED,
		data=event_data,
		user_id=reminder.owner_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)


def _reminder_occurrence_item(
	reminder: Reminder,
	original_occurrence_at: datetime,
	effective_start_at: datetime,
	color: str | None,
	status_value: ReminderStatus,
	completed_at: datetime | None,
) -> ScheduledItem:
	return ScheduledItem(
		kind="reminder",
		id=_occurrence_id(reminder.id, original_occurrence_at),
		parent_id=reminder.id,
		container_id=reminder.list_id,
		reminder_list_id=reminder.list_id,
		original_occurrence_at=original_occurrence_at,
		effective_start_at=effective_start_at,
		effective_end_at=None,
		all_day=False,
		title=reminder.title,
		description=reminder.description,
		color=color,
		status=status_value,
		readonly=True,
		completed_at=completed_at,
	)


def _occurrence_id(reminder_id: TypeID, original_occurrence_at: datetime) -> str:
	return f"reminder:{reminder_id}:{original_occurrence_at.isoformat()}"


async def delete_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a reminder and its subtasks."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	descendants = await _load_reminder_descendants(reminder.id, session)
	reminder_id_str = str(reminder.id)
	list_id_str = str(reminder.list_id)
	reminder_ids_to_invalidate = [
		reminder.id,
		*[descendant.id for descendant in descendants],
	]

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_DELETED,
		data={
			"id": reminder_id_str,
			"list_id": list_id_str,
			"deleted_descendant_ids": [
				str(descendant.id) for descendant in descendants
			],
		},
		user_id=principal.user_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await _invalidate_reminders(reminder_ids_to_invalidate)
	for deleted_reminder_id in reminder_ids_to_invalidate:
		await cancel_reminder_notifications(deleted_reminder_id)

	for descendant in descendants:
		await remove_vectorized_resource(
			REMINDER_SPEC,
			resource_id=str(descendant.id),
			session=session,
		)
	await remove_vectorized_resource(
		REMINDER_SPEC, resource_id=reminder_id_str, session=session
	)
	for descendant in descendants:
		await session.delete(descendant)
	await session.delete(reminder)
	await session.flush()


async def _load_reminder_descendants(
	reminder_id: TypeID,
	session: AsyncSession,
) -> list[Reminder]:
	descendants: list[Reminder] = []
	frontier = {reminder_id}
	seen = {reminder_id}
	depth = 0
	while frontier:
		result = await session.execute(
			select(Reminder).where(Reminder.parent_id.in_(frontier))
		)
		children = list(result.scalars().all())
		if not children:
			break
		next_frontier: set[TypeID] = set()
		for child in children:
			child_id = TypeID(child.id)
			if child_id in seen:
				raise _hierarchy_cycle_error()
			seen.add(child_id)
			next_frontier.add(child_id)
			descendants.append(child)
		depth += 1
		if depth > _max_hierarchy_depth():
			raise _hierarchy_limit_error()
		frontier = next_frontier
	return descendants


async def move_reminder(
	reminder_id: TypeID,
	target_list_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	position: float | None = None,
	origin_session_id: str | None = None,
) -> Reminder:
	"""move a reminder to a different list."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	previous_list_id = reminder.list_id

	await get_reminder_list(target_list_id, session, principal=principal)

	descendants = await _load_reminder_descendants(reminder.id, session)
	reminder.list_id = target_list_id
	for descendant in descendants:
		descendant.list_id = target_list_id
	if position is not None:
		reminder.position = position

	await session.flush()
	await session.refresh(reminder)

	event_data: dict[str, object] = {
		"id": str(reminder.id),
		"list_id": str(target_list_id),
		"updated_at": reminder.updated_at.isoformat(),
		"previous_list_id": str(previous_list_id) if previous_list_id else None,
	}
	if descendants:
		event_data["moved_descendant_ids"] = [
			str(descendant.id) for descendant in descendants
		]
	if position is not None:
		event_data["position"] = position
	reminder_ids_to_invalidate = [
		reminder.id,
		*[descendant.id for descendant in descendants],
	]
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_UPDATED,
		data=event_data,
		user_id=principal.user_id,
		reminder_id=reminder.id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await _invalidate_reminders(reminder_ids_to_invalidate)
	await vectorize_resource(spec=REMINDER_SPEC, resource=reminder, session=session)
	for descendant in descendants:
		await vectorize_resource(
			spec=REMINDER_SPEC,
			resource=descendant,
			session=session,
		)

	return reminder
