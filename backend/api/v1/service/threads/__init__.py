"""thread service facade"""

from api.models.thread import Thread
from api.schemas.thread import BranchPage, ThreadUpdate
from api.v1.service.threads.addressing import (
	message_mentions_agent,
	resolve_invoked_agents,
)
from api.v1.service.threads.agents import (
	add_agents,
	remove_agent,
	update_agent_participant,
)
from api.v1.service.threads.branches import (
	get_branch_page,
	list_message_siblings,
	switch_branch,
)
from api.v1.service.threads.common import (
	is_multi_writer_thread,
	message_payloads,
	multi_writer_thread_ids,
)
from api.v1.service.threads.content_vectors import (
	purge_thread_content_vectors,
	reconcile_thread_content_vectors,
)
from api.v1.service.threads.core import (
	count_threads,
	delete_thread,
	filter_active_thread_ids,
	get_thread,
	get_thread_payload,
	list_threads,
	restore_thread,
	update_thread,
)
from api.v1.service.threads.create import (
	create_thread,
)
from api.v1.service.threads.drafts import MessageDraft
from api.v1.service.threads.invites import (
	accept_invite,
	block_invite,
	decline_invite,
)
from api.v1.service.threads.members import (
	add_members,
	build_thread_payload,
	build_thread_payloads,
	human_roster_labels,
	list_participants,
	remove_member,
	thread_payloads,
)
from api.v1.service.threads.messages import (
	create_message,
	create_message_at_run_tail,
	delete_user_message_turn,
	get_message,
	list_events_for_message_ids,
	list_message_tree,
	list_messages,
	update_user_message,
)
from api.v1.service.threads.passages import (
	get_thread_passage,
	list_thread_passages,
	update_thread_passage_enrichment,
)
from api.v1.service.threads.search import (
	THREAD_SPEC,
	search_threads,
	thread_to_search_item,
	vectorize_stale_threads,
	vectorize_threads,
)
from api.v1.service.threads.splices import (
	apply_existing_message_splice,
)
from api.v1.service.threads.tree import (
	active_branch_message_ids,
	branch_root_id,
	get_current_branch,
	load_thread_with_branch,
	message_is_visible,
	messages_between,
	require_run_context_message,
	visible_message_ids,
	walk_message_branch,
)
from api.v1.service.threads.user_state import (
	ensure_participant,
	get_unread_counts,
	handle_typing_event,
	mark_thread_read,
	update_thread_participant,
)


__all__ = [
	"accept_invite",
	"active_branch_message_ids",
	"add_agents",
	"add_members",
	"apply_existing_message_splice",
	"block_invite",
	"branch_root_id",
	"BranchPage",
	"build_thread_payload",
	"build_thread_payloads",
	"count_threads",
	"create_message",
	"create_message_at_run_tail",
	"create_thread",
	"decline_invite",
	"delete_thread",
	"delete_user_message_turn",
	"ensure_participant",
	"filter_active_thread_ids",
	"get_branch_page",
	"get_current_branch",
	"get_message",
	"get_thread",
	"get_thread_passage",
	"get_thread_payload",
	"get_unread_counts",
	"handle_typing_event",
	"human_roster_labels",
	"is_multi_writer_thread",
	"list_events_for_message_ids",
	"list_message_siblings",
	"list_message_tree",
	"list_messages",
	"list_participants",
	"list_thread_passages",
	"list_threads",
	"load_thread_with_branch",
	"mark_thread_read",
	"message_is_visible",
	"message_mentions_agent",
	"message_payloads",
	"MessageDraft",
	"messages_between",
	"multi_writer_thread_ids",
	"purge_thread_content_vectors",
	"reconcile_thread_content_vectors",
	"remove_agent",
	"remove_member",
	"require_run_context_message",
	"resolve_invoked_agents",
	"restore_thread",
	"search_threads",
	"switch_branch",
	"Thread",
	"thread_payloads",
	"THREAD_SPEC",
	"thread_to_search_item",
	"ThreadUpdate",
	"update_agent_participant",
	"update_thread",
	"update_thread_participant",
	"update_thread_passage_enrichment",
	"update_user_message",
	"vectorize_stale_threads",
	"vectorize_threads",
	"visible_message_ids",
	"walk_message_branch",
]
