"""calendar service facade."""

from api.models.calendar import Calendar, CalendarEvent, CalendarEventOverride
from api.schemas.calendar import CalendarEventUpdate, CalendarUpdate
from api.v1.service.calendar.calendars import (
	count_calendars,
	create_calendar,
	delete_calendar,
	get_calendar,
	list_calendars,
	update_calendar,
)
from api.v1.service.calendar.events import (
	cancel_calendar_event_occurrence,
	create_calendar_event,
	delete_calendar_event,
	edit_calendar_event_occurrence,
	edit_calendar_event_series,
	get_calendar_event,
	list_calendar_events,
	update_calendar_event,
)
from api.v1.service.calendar.search import (
	CALENDAR_EVENT_SPEC,
	calendar_event_to_search_item,
	search_calendar_events,
	vectorize_all_calendar_events,
	vectorize_calendar_events_for_calendar,
)


__all__ = [
	"CALENDAR_EVENT_SPEC",
	"Calendar",
	"CalendarEvent",
	"CalendarEventOverride",
	"CalendarEventUpdate",
	"CalendarUpdate",
	"cancel_calendar_event_occurrence",
	"count_calendars",
	"create_calendar",
	"create_calendar_event",
	"delete_calendar",
	"delete_calendar_event",
	"edit_calendar_event_occurrence",
	"edit_calendar_event_series",
	"get_calendar",
	"get_calendar_event",
	"list_calendar_events",
	"list_calendars",
	"calendar_event_to_search_item",
	"search_calendar_events",
	"update_calendar",
	"update_calendar_event",
	"vectorize_all_calendar_events",
	"vectorize_calendar_events_for_calendar",
]
