"""TaskIQ task registry imports.

Import this module in worker and scheduler processes to register all durable
task runners and scheduled jobs with the shared broker.
"""

from api.v1.service import tasks as _task_runtime
from api.v1.tasks import calendar as _calendar_tasks
from api.v1.tasks import open_webui as _open_webui_tasks
from api.v1.tasks import reminders as _reminder_tasks
from api.v1.tasks import threads as _thread_tasks


__all__ = []

_ = (
	_task_runtime,
	_calendar_tasks,
	_open_webui_tasks,
	_reminder_tasks,
	_thread_tasks,
)
