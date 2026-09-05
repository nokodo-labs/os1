"""authorization service package.

only names with consumers outside this package are re-exported. inside the
package, and in tests that reach for internals, import from the defining module
by its full path.
"""

from api.v1.service.authorization.cache import (
	enqueue_accessible_users_invalidation_for_subject,
	invalidate_accessible_users_for_refs,
	invalidate_accessible_users_for_resource,
	invalidate_accessible_users_for_resource_types,
	invalidate_accessible_users_for_role_defaults,
	list_accessible_user_ids_for_resources,
	list_resource_access_user_ids_for_resources,
	resolve_accessible_user_ids,
	resolve_resource_access_user_ids,
	resource_refs_for_subject,
)
from api.v1.service.authorization.changes import (
	AccessChangeEventEnrichment,
	AccessChangeFinalizer,
	AccessChangeSnapshot,
	PreparedAccessChange,
	ResolvedAccessShape,
	ResourceRef,
	build_access_change_events,
	capture_access_change,
	current_access_revision,
	read_access_change_batch,
	register_access_change_hook,
)
from api.v1.service.authorization.config import (
	ACL_RESOURCE_TYPES,
	CONTAINED_LEVELS,
	LEAF_RESOURCE_TYPES,
	READ_ONLY_LEVELS,
	RESOURCE_CONFIG,
	ACLResourceConfig,
	ResourceConfig,
	allowed_levels,
	changed_default_access_resource_types,
	default_access_resource_types,
	level_satisfies,
)
from api.v1.service.authorization.inheritance import (
	load_parent_resource_refs,
)
from api.v1.service.authorization.metadata import (
	ACL_REVISION_KEY,
	ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES,
	VECTOR_CHUNK_ACCESS_RESOURCE_TYPES,
	VECTOR_CHUNK_PARENT_RESOURCE_TYPES,
	fetch_bulk_acl_metadata,
	fetch_bulk_acl_revisions,
	vector_acl_filter,
)
from api.v1.service.authorization.predicates import (
	apply_resource_access_list_filters,
	resource_access_predicate,
	resource_derived_access_predicate,
)
from api.v1.service.authorization.projection import (
	apply_metadata_write,
	project_private,
	public_payload,
	require_private_write,
)
from api.v1.service.authorization.resolve import (
	AccessGraphCache,
	get_effective_access_level,
	require_admin,
	require_permission,
	require_project_access,
	require_resource_access,
	require_self_or_permission,
	require_thread_access,
)


__all__ = [
	"ACL_REVISION_KEY",
	"ACLResourceConfig",
	"AccessChangeSnapshot",
	"AccessGraphCache",
	"AccessChangeFinalizer",
	"AccessChangeEventEnrichment",
	"PreparedAccessChange",
	"ResolvedAccessShape",
	"ResourceRef",
	"ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES",
	"ACL_RESOURCE_TYPES",
	"CONTAINED_LEVELS",
	"LEAF_RESOURCE_TYPES",
	"READ_ONLY_LEVELS",
	"RESOURCE_CONFIG",
	"ResourceConfig",
	"VECTOR_CHUNK_PARENT_RESOURCE_TYPES",
	"VECTOR_CHUNK_ACCESS_RESOURCE_TYPES",
	"enqueue_accessible_users_invalidation_for_subject",
	"allowed_levels",
	"apply_metadata_write",
	"apply_resource_access_list_filters",
	"build_access_change_events",
	"capture_access_change",
	"current_access_revision",
	"changed_default_access_resource_types",
	"default_access_resource_types",
	"fetch_bulk_acl_metadata",
	"fetch_bulk_acl_revisions",
	"get_effective_access_level",
	"invalidate_accessible_users_for_resource",
	"invalidate_accessible_users_for_refs",
	"invalidate_accessible_users_for_resource_types",
	"invalidate_accessible_users_for_role_defaults",
	"level_satisfies",
	"list_accessible_user_ids_for_resources",
	"list_resource_access_user_ids_for_resources",
	"resolve_accessible_user_ids",
	"resolve_resource_access_user_ids",
	"load_parent_resource_refs",
	"project_private",
	"public_payload",
	"require_admin",
	"require_permission",
	"require_private_write",
	"require_project_access",
	"require_resource_access",
	"require_self_or_permission",
	"require_thread_access",
	"register_access_change_hook",
	"read_access_change_batch",
	"resource_access_predicate",
	"resource_derived_access_predicate",
	"resource_refs_for_subject",
	"vector_acl_filter",
]
