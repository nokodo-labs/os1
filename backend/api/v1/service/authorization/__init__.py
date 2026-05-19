"""authorization service package."""

from api.v1.service.authorization.cache import (
	accessible_users_tag,
	invalidate_accessible_users_for_resource,
	invalidate_accessible_users_for_resource_types,
	invalidate_accessible_users_for_role_defaults,
	invalidate_accessible_users_for_subject,
	list_accessible_user_ids,
)
from api.v1.service.authorization.config import (
	RESOURCE_CONFIG,
	ResourceConfig,
	allowed_levels,
	changed_default_access_resource_types,
	default_access_resource_types,
	level_satisfies,
	unique_resource_types,
)
from api.v1.service.authorization.inheritance import (
	inherited_parent_resource_types,
	load_descendant_resource_ids,
	load_parent_resource_refs,
)
from api.v1.service.authorization.metadata import (
	ACLPrincipalMetadata,
	empty_acl_metadata,
	fetch_acl_metadata,
	fetch_bulk_acl_metadata,
	merge_acl_metadata,
	vector_acl_filter,
)
from api.v1.service.authorization.predicates import (
	project_access_predicate,
	resource_access_predicate,
	thread_access_predicate,
)
from api.v1.service.authorization.resolve import (
	get_effective_access_level,
	require_admin,
	require_permission,
	require_project_access,
	require_resource_access,
	require_thread_access,
	resolve_effective_level,
)


__all__ = [
	"ACLPrincipalMetadata",
	"RESOURCE_CONFIG",
	"ResourceConfig",
	"accessible_users_tag",
	"allowed_levels",
	"changed_default_access_resource_types",
	"default_access_resource_types",
	"empty_acl_metadata",
	"fetch_acl_metadata",
	"fetch_bulk_acl_metadata",
	"get_effective_access_level",
	"inherited_parent_resource_types",
	"invalidate_accessible_users_for_resource",
	"invalidate_accessible_users_for_resource_types",
	"invalidate_accessible_users_for_role_defaults",
	"invalidate_accessible_users_for_subject",
	"level_satisfies",
	"list_accessible_user_ids",
	"load_descendant_resource_ids",
	"load_parent_resource_refs",
	"merge_acl_metadata",
	"project_access_predicate",
	"require_admin",
	"require_permission",
	"require_project_access",
	"require_resource_access",
	"require_thread_access",
	"resolve_effective_level",
	"resource_access_predicate",
	"thread_access_predicate",
	"unique_resource_types",
	"vector_acl_filter",
]
