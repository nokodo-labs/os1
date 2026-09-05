"""resource configuration shared by authorization helpers."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeIs

from sqlalchemy.orm import InstrumentedAttribute

from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.calendar import Calendar, CalendarEvent
from api.models.file import File
from api.models.group import Group
from api.models.memory import Memory
from api.models.message import Message
from api.models.message_attachment import MessageAttachment
from api.models.note import Note
from api.models.plugin import Plugin
from api.models.project import Project
from api.models.prompt import Prompt
from api.models.reminder import Reminder, ReminderList
from api.models.task import Task
from api.models.thread import Thread
from api.permissions import (
	ATTACHABLE_RESOURCE_TYPES,
	DEFAULT_ACCESS_RESOURCE_TYPES,
	DefaultResourceAccess,
	ResourceType,
	higher_access,
	level_satisfies,
)


@dataclass(frozen=True, slots=True)
class ParentGrant:
	"""one way to earn a child level, optionally gated on authoring the row."""

	parent_level: AccessLevel
	requires_author: bool = False


type InheritedLevels = Mapping[AccessLevel, tuple[ParentGrant, ...]]
"""per child level, the alternative ways a parent can confer it.

a level absent from the table is never inherited through that edge. this table is
the shared declaration that every authorization engine interprets.
"""


MAX_INHERITANCE_DEPTH = 16
"""maximum parent links traversed by one authorization path."""


CONTAINED_LEVELS: InheritedLevels = MappingProxyType(
	{
		AccessLevel.READER: (ParentGrant(AccessLevel.READER),),
		AccessLevel.EDITOR: (ParentGrant(AccessLevel.EDITOR),),
		AccessLevel.ADMIN: (ParentGrant(AccessLevel.ADMIN),),
	}
)
"""identity: the child is part of the parent, so levels pass through."""

READ_ONLY_LEVELS: InheritedLevels = MappingProxyType(
	{
		AccessLevel.READER: (ParentGrant(AccessLevel.READER),),
	}
)
"""reference-only: reaching a resource this way never grants more than read."""

AUTHORED_LEVELS: InheritedLevels = MappingProxyType(
	{
		AccessLevel.READER: (ParentGrant(AccessLevel.READER),),
		AccessLevel.EDITOR: (
			ParentGrant(AccessLevel.ADMIN),
			ParentGrant(AccessLevel.EDITOR, requires_author=True),
		),
		AccessLevel.ADMIN: (ParentGrant(AccessLevel.ADMIN),),
	}
)
"""the child has a responsible author, so peers cannot edit each other's rows."""


@dataclass(frozen=True, slots=True)
class ResourceConfig:
	"""config for a resource type's access control.

	this is the ONE registry for per-resource-type access settings: add a field
	here rather than a side map or an inline match statement elsewhere, so a
	new resource type cannot silently miss a behaviour.
	"""

	id_col: InstrumentedAttribute
	deleted_at_col: InstrumentedAttribute | None
	parent_type: ResourceType | None = None
	parent_fk: InstrumentedAttribute | None = None
	inherited_levels: InheritedLevels | None = None
	author_fk: InstrumentedAttribute | None = None
	attachment_fk: InstrumentedAttribute | None = None
	origin_message_fk: InstrumentedAttribute | None = None
	hidden_col: InstrumentedAttribute | None = None
	access_lock_namespace: str | None = None
	acl_list_visibility: AccessLevel = AccessLevel.ADMIN
	"""minimum effective level required to READ this resource's rule list.

	visibility and management are separate axes: mutation always requires
	ADMIN. operators intentionally receive access events for every resource they
	may inspect so connected administrative views remain live.
	"""


@dataclass(frozen=True, slots=True, kw_only=True)
class ACLResourceConfig(ResourceConfig):
	"""configuration for a resource that owns access rules."""

	rule_fk: InstrumentedAttribute
	owner_fk: InstrumentedAttribute | None


@dataclass(frozen=True, slots=True, kw_only=True)
class LeafResourceConfig(ResourceConfig):
	"""configuration for a resource whose access comes from its parent."""

	parent_type: ResourceType
	parent_fk: InstrumentedAttribute
	inherited_levels: InheritedLevels


RESOURCE_CONFIG: Mapping[ResourceType, ResourceConfig] = MappingProxyType(
	{
		ResourceType.THREAD: ACLResourceConfig(
			id_col=Thread.id,
			rule_fk=AccessRule.thread_id,
			owner_fk=Thread.owner_id,
			deleted_at_col=Thread.deleted_at,
			attachment_fk=MessageAttachment.thread_id,
			origin_message_fk=Thread.origin_message_id,
			hidden_col=Thread.is_temporary,
			# conversations: the rules ARE the member roster, so any member sees
			# the full list. other types stay admin-only until decided per type.
			acl_list_visibility=AccessLevel.READER,
			access_lock_namespace="thread",
		),
		ResourceType.MESSAGE: LeafResourceConfig(
			id_col=Message.id,
			deleted_at_col=None,
			parent_type=ResourceType.THREAD,
			parent_fk=Message.thread_id,
			inherited_levels=AUTHORED_LEVELS,
			author_fk=Message.sender_user_id,
		),
		ResourceType.PROJECT: ACLResourceConfig(
			id_col=Project.id,
			rule_fk=AccessRule.project_id,
			owner_fk=Project.owner_id,
			deleted_at_col=None,
			attachment_fk=MessageAttachment.project_id,
			origin_message_fk=Project.origin_message_id,
		),
		ResourceType.AGENT: ACLResourceConfig(
			id_col=Agent.id,
			rule_fk=AccessRule.agent_id,
			owner_fk=None,
			deleted_at_col=None,
		),
		ResourceType.NOTE: ACLResourceConfig(
			id_col=Note.id,
			rule_fk=AccessRule.note_id,
			owner_fk=Note.user_id,
			deleted_at_col=Note.deleted_at,
			attachment_fk=MessageAttachment.note_id,
			origin_message_fk=Note.origin_message_id,
		),
		ResourceType.MEMORY: ACLResourceConfig(
			id_col=Memory.id,
			rule_fk=AccessRule.memory_id,
			owner_fk=Memory.user_id,
			deleted_at_col=None,
		),
		ResourceType.TASK: ACLResourceConfig(
			id_col=Task.id,
			rule_fk=AccessRule.task_id,
			owner_fk=Task.user_id,
			deleted_at_col=None,
		),
		ResourceType.FILE: ACLResourceConfig(
			id_col=File.id,
			rule_fk=AccessRule.file_id,
			owner_fk=File.owner_id,
			deleted_at_col=File.deleted_at,
			attachment_fk=MessageAttachment.file_id,
			origin_message_fk=File.origin_message_id,
		),
		ResourceType.CALENDAR: ACLResourceConfig(
			id_col=Calendar.id,
			rule_fk=AccessRule.calendar_id,
			owner_fk=Calendar.owner_id,
			deleted_at_col=None,
			attachment_fk=MessageAttachment.calendar_id,
			origin_message_fk=Calendar.origin_message_id,
		),
		ResourceType.CALENDAR_EVENT: LeafResourceConfig(
			id_col=CalendarEvent.id,
			deleted_at_col=None,
			parent_type=ResourceType.CALENDAR,
			parent_fk=CalendarEvent.calendar_id,
			inherited_levels=CONTAINED_LEVELS,
			attachment_fk=MessageAttachment.calendar_event_id,
			origin_message_fk=CalendarEvent.origin_message_id,
		),
		ResourceType.PLUGIN: ACLResourceConfig(
			id_col=Plugin.id,
			rule_fk=AccessRule.plugin_id,
			owner_fk=None,
			deleted_at_col=None,
		),
		ResourceType.PROMPT: ACLResourceConfig(
			id_col=Prompt.id,
			rule_fk=AccessRule.prompt_id,
			owner_fk=None,
			deleted_at_col=None,
		),
		ResourceType.GROUP: ACLResourceConfig(
			id_col=Group.id,
			rule_fk=AccessRule.group_id,
			owner_fk=Group.owner_id,
			deleted_at_col=None,
		),
		ResourceType.REMINDER_LIST: ACLResourceConfig(
			id_col=ReminderList.id,
			rule_fk=AccessRule.reminder_list_id,
			owner_fk=ReminderList.owner_id,
			deleted_at_col=None,
			attachment_fk=MessageAttachment.reminder_list_id,
			origin_message_fk=ReminderList.origin_message_id,
		),
		ResourceType.REMINDER: LeafResourceConfig(
			id_col=Reminder.id,
			deleted_at_col=None,
			parent_type=ResourceType.REMINDER_LIST,
			parent_fk=Reminder.list_id,
			inherited_levels=CONTAINED_LEVELS,
			attachment_fk=MessageAttachment.reminder_id,
			origin_message_fk=Reminder.origin_message_id,
		),
	}
)


def inherited_child_level(
	levels: InheritedLevels,
	parent_level: AccessLevel,
	is_author: bool,
) -> AccessLevel | None:
	"""evaluate an inheritance table in python.

	the counterpart to the SQL the predicate builder emits from the same table:
	both must agree, so both read this one declaration.
	"""
	result: AccessLevel | None = None
	for child_level, grants in levels.items():
		for grant in grants:
			if grant.requires_author and not is_author:
				continue
			if level_satisfies(parent_level, grant.parent_level):
				result = higher_access(result, child_level)
				break
	return result


def is_acl_resource_config(config: ResourceConfig) -> TypeIs[ACLResourceConfig]:
	"""return whether a resource owns access rules."""
	return isinstance(config, ACLResourceConfig)


def is_leaf_resource_config(config: ResourceConfig) -> TypeIs[LeafResourceConfig]:
	"""return whether a resource derives access from a parent."""
	return isinstance(config, LeafResourceConfig)


ACL_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(
	resource_type
	for resource_type, config in RESOURCE_CONFIG.items()
	if is_acl_resource_config(config)
)
"""resource types that own access rules."""


LEAF_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(
	resource_type
	for resource_type, config in RESOURCE_CONFIG.items()
	if is_leaf_resource_config(config)
)
"""resource types whose access is derived from a parent."""


if {
	resource_type
	for resource_type, config in RESOURCE_CONFIG.items()
	if config.attachment_fk is not None
} != ATTACHABLE_RESOURCE_TYPES:
	raise RuntimeError("attachable resource configuration is incomplete")


if {
	resource_type
	for resource_type, config in RESOURCE_CONFIG.items()
	if config.origin_message_fk is not None
} != ATTACHABLE_RESOURCE_TYPES:
	raise RuntimeError("origin resource configuration is incomplete")


def allowed_levels(required: AccessLevel) -> tuple[AccessLevel, ...]:
	"""return all access levels that satisfy the required level."""
	match required:
		case AccessLevel.READER:
			return (AccessLevel.READER, AccessLevel.EDITOR, AccessLevel.ADMIN)
		case AccessLevel.EDITOR:
			return (AccessLevel.EDITOR, AccessLevel.ADMIN)
		case AccessLevel.ADMIN:
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
	"""return resource types granted by one default-access configuration."""
	return [
		resource_type
		for resource_type in DEFAULT_ACCESS_RESOURCE_TYPES
		if defaults.get(resource_type) is not None
	]


def resource_access_lock_namespace(resource_type: ResourceType) -> str:
	"""return the advisory-lock namespace for one resource type."""
	config = RESOURCE_CONFIG[resource_type]
	return config.access_lock_namespace or f"{resource_type.value}:access"
