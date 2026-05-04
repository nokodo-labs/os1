"""reminder service facade."""

from api.models.reminder import Reminder, ReminderList, ReminderOverride, ReminderStatus
from api.schemas.reminder import ReminderUpdate
from api.v1.service.reminders.core import (
	complete_reminder,
	complete_reminder_occurrence,
	create_reminder,
	delete_reminder,
	edit_reminder_series,
	get_reminder,
	list_reminders,
	list_scheduled_reminders,
	move_reminder,
	update_reminder,
)
from api.v1.service.reminders.lists import (
	create_reminder_list,
	delete_reminder_list,
	get_list_counts,
	get_or_create_default_reminder_list,
	get_reminder_list,
	list_reminder_lists,
	update_reminder_list,
)
from api.v1.service.reminders.search import (
	REMINDER_SPEC,
	search_reminders,
	vectorize_all_reminders,
	vectorize_reminders_for_list,
)


__all__ = [
	"REMINDER_SPEC",
	"Reminder",
	"ReminderList",
	"ReminderOverride",
	"ReminderStatus",
	"ReminderUpdate",
	"complete_reminder",
	"complete_reminder_occurrence",
	"create_reminder",
	"create_reminder_list",
	"delete_reminder",
	"delete_reminder_list",
	"edit_reminder_series",
	"get_list_counts",
	"get_or_create_default_reminder_list",
	"get_reminder",
	"get_reminder_list",
	"list_reminder_lists",
	"list_reminders",
	"list_scheduled_reminders",
	"move_reminder",
	"search_reminders",
	"update_reminder",
	"update_reminder_list",
	"vectorize_all_reminders",
	"vectorize_reminders_for_list",
]
