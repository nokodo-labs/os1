"""thread service facade."""

from api.models.thread import Thread
from api.schemas.thread import ThreadUpdate
from api.v1.service.threads.core import (
	count_threads,
	create_thread,
	delete_thread,
	get_thread,
	get_thread_payload,
	list_threads,
	update_thread,
)
from api.v1.service.threads.maintenance import (
	list_threads_due_for_maintenance,
	maintain_thread_metadata,
	thread_needs_deferred_maintenance,
	thread_needs_maintenance,
	thread_needs_mandatory_maintenance,
)
from api.v1.service.threads.messages import (
	create_message,
	delete_user_message_turn,
	get_current_branch,
	list_events_for_message_ids,
	list_message_tree,
	list_messages,
	load_thread_with_branch,
	switch_branch,
	update_user_message,
	walk_message_branch,
)
from api.v1.service.threads.metadata import (
	generate_thread_metadata,
	thread_metadata_missing,
)
from api.v1.service.threads.participants import (
	ensure_participant,
	get_unread_counts,
	handle_typing_event,
	mark_thread_read,
)
from api.v1.service.threads.search import (
	THREAD_SPEC,
	search_threads,
	vectorize_all_threads,
)


__all__ = [
	"THREAD_SPEC",
	"Thread",
	"ThreadUpdate",
	"count_threads",
	"create_message",
	"create_thread",
	"delete_thread",
	"delete_user_message_turn",
	"ensure_participant",
	"generate_thread_metadata",
	"get_current_branch",
	"get_thread",
	"get_thread_payload",
	"get_unread_counts",
	"handle_typing_event",
	"list_events_for_message_ids",
	"list_message_tree",
	"list_messages",
	"list_threads",
	"list_threads_due_for_maintenance",
	"load_thread_with_branch",
	"maintain_thread_metadata",
	"mark_thread_read",
	"search_threads",
	"switch_branch",
	"thread_metadata_missing",
	"thread_needs_deferred_maintenance",
	"thread_needs_mandatory_maintenance",
	"thread_needs_maintenance",
	"update_thread",
	"update_user_message",
	"vectorize_all_threads",
	"walk_message_branch",
]
