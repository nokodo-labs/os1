"""resource configuration shared by authorization helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import InstrumentedAttribute

from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.calendar import Calendar
from api.models.file import File
from api.models.group import Group
from api.models.memory import Memory
from api.models.note import Note
from api.models.plugin import Plugin
from api.models.project import Project
from api.models.prompt import Prompt
from api.models.reminder import ReminderList
from api.models.task import Task
from api.models.thread import Thread
from api.permissions import (
	DEFAULT_ACCESS_RESOURCE_TYPES,
	DefaultResourceAccess,
	ResourceType,
)


@dataclass(frozen=True, slots=True)
class ResourceConfig:
	"""config for a resource type's access control."""

	id_col: InstrumentedAttribute
	rule_fk: InstrumentedAttribute
	owner_fk: InstrumentedAttribute | None
	deleted_at_col: InstrumentedAttribute | None


RESOURCE_CONFIG: dict[ResourceType, ResourceConfig] = {
	ResourceType.THREAD: ResourceConfig(
		id_col=Thread.id,
		rule_fk=AccessRule.thread_id,
		owner_fk=Thread.owner_id,
		deleted_at_col=Thread.deleted_at,
	),
	ResourceType.PROJECT: ResourceConfig(
		id_col=Project.id,
		rule_fk=AccessRule.project_id,
		owner_fk=Project.owner_id,
		deleted_at_col=None,
	),
	ResourceType.AGENT: ResourceConfig(
		id_col=Agent.id,
		rule_fk=AccessRule.agent_id,
		owner_fk=None,
		deleted_at_col=None,
	),
	ResourceType.NOTE: ResourceConfig(
		id_col=Note.id,
		rule_fk=AccessRule.note_id,
		owner_fk=Note.user_id,
		deleted_at_col=Note.deleted_at,
	),
	ResourceType.MEMORY: ResourceConfig(
		id_col=Memory.id,
		rule_fk=AccessRule.memory_id,
		owner_fk=Memory.user_id,
		deleted_at_col=None,
	),
	ResourceType.TASK: ResourceConfig(
		id_col=Task.id,
		rule_fk=AccessRule.task_id,
		owner_fk=Task.user_id,
		deleted_at_col=None,
	),
	ResourceType.FILE: ResourceConfig(
		id_col=File.id,
		rule_fk=AccessRule.file_id,
		owner_fk=File.owner_id,
		deleted_at_col=File.deleted_at,
	),
	ResourceType.CALENDAR: ResourceConfig(
		id_col=Calendar.id,
		rule_fk=AccessRule.calendar_id,
		owner_fk=Calendar.owner_id,
		deleted_at_col=None,
	),
	ResourceType.PLUGIN: ResourceConfig(
		id_col=Plugin.id,
		rule_fk=AccessRule.plugin_id,
		owner_fk=None,
		deleted_at_col=None,
	),
	ResourceType.PROMPT: ResourceConfig(
		id_col=Prompt.id,
		rule_fk=AccessRule.prompt_id,
		owner_fk=None,
		deleted_at_col=None,
	),
	ResourceType.GROUP: ResourceConfig(
		id_col=Group.id,
		rule_fk=AccessRule.group_id,
		owner_fk=Group.owner_id,
		deleted_at_col=None,
	),
	ResourceType.REMINDER_LIST: ResourceConfig(
		id_col=ReminderList.id,
		rule_fk=AccessRule.reminder_list_id,
		owner_fk=ReminderList.owner_id,
		deleted_at_col=None,
	),
}


def level_satisfies(granted: AccessLevel, required: AccessLevel) -> bool:
	"""check if granted access level satisfies the required level."""
	level_order = {AccessLevel.READER: 0, AccessLevel.EDITOR: 1, AccessLevel.ADMIN: 2}
	return level_order[granted] >= level_order[required]


def allowed_levels(required: AccessLevel) -> tuple[AccessLevel, ...]:
	"""return all access levels that satisfy the required level."""
	match required:
		case AccessLevel.READER:
			return (AccessLevel.READER, AccessLevel.EDITOR, AccessLevel.ADMIN)
		case AccessLevel.EDITOR:
			return (AccessLevel.EDITOR, AccessLevel.ADMIN)
		case AccessLevel.ADMIN:
			return (AccessLevel.ADMIN,)
		case _:
			return (AccessLevel.ADMIN,)


def changed_default_access_resource_types(
	previous: DefaultResourceAccess,
	current: DefaultResourceAccess,
) -> list[ResourceType]:
	"""return resource types whose default access level changed."""
	return [
		resource_type
		for resource_type in DEFAULT_ACCESS_RESOURCE_TYPES
		if previous.get(resource_type) != current.get(resource_type)
	]


def default_access_resource_types(
	defaults: DefaultResourceAccess,
) -> list[ResourceType]:
	return [
		resource_type
		for resource_type in DEFAULT_ACCESS_RESOURCE_TYPES
		if defaults.get(resource_type) is not None
	]


def unique_resource_types(resource_types: list[ResourceType]) -> list[ResourceType]:
	result: list[ResourceType] = []
	for resource_type in resource_types:
		if resource_type not in result:
			result.append(resource_type)
	return result
