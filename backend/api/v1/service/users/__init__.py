"""user service operations."""

from api.v1.service.users.accounts import (
	change_email,
	change_password,
	count_users,
	create_user,
	delete_user,
	get_accessible_user_summaries,
	get_user,
	get_user_counts,
	list_users,
	update_user,
)
from api.v1.service.users.clients import (
	delete_user_client,
	list_user_clients,
	update_user_client,
	update_user_client_preferences,
	upsert_user_client,
)
from api.v1.service.users.presence import (
	count_active_users,
	is_user_active,
	list_active_user_ids,
	mark_user_active,
	mark_user_inactive,
	touch_user_activity,
)
from api.v1.service.users.sessions import (
	list_user_sessions,
	revoke_user_session,
	revoke_user_sessions,
)


__all__ = [
	"change_email",
	"change_password",
	"count_active_users",
	"count_users",
	"create_user",
	"delete_user",
	"delete_user_client",
	"get_accessible_user_summaries",
	"get_user",
	"get_user_counts",
	"is_user_active",
	"list_active_user_ids",
	"list_user_clients",
	"list_user_sessions",
	"list_users",
	"mark_user_active",
	"mark_user_inactive",
	"revoke_user_session",
	"revoke_user_sessions",
	"touch_user_activity",
	"update_user",
	"update_user_client",
	"update_user_client_preferences",
	"upsert_user_client",
]
