"""SQL predicates for social user visibility and discovery."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, true
from sqlalchemy.sql import ColumnElement

from api.models.user import User
from api.schemas.privacy import PrivacyField, Visibility, privacy_field_default
from api.v1.service.auth import Principal
from api.v1.service.social.friendship import accepted_friendship_exists, block_exists


def user_unblocked_predicate(principal: Principal) -> ColumnElement[bool]:
	"""return a predicate excluding users blocked in either direction."""
	if principal.is_admin:
		return true()
	return ~block_exists(principal.user_id, User.id)


def user_search_candidate_predicate(
	principal: Principal,
	include_inactive: bool = False,
) -> ColumnElement[bool]:
	"""return users that may appear in social search candidates."""
	if principal.is_admin:
		return true()
	active = true() if include_inactive else User.is_active.is_(True)
	return and_(active, user_unblocked_predicate(principal))


def _user_privacy_value(field: PrivacyField) -> ColumnElement[str]:
	"""return a privacy JSONB field with its schema default applied."""
	return func.coalesce(
		User.privacy[field].as_string(), privacy_field_default(field).value
	)


def user_privacy_visibility_predicate(
	principal: Principal,
	field: PrivacyField,
) -> ColumnElement[bool]:
	"""return whether a candidate user's privacy field is visible."""
	if principal.is_admin:
		return true()
	value = _user_privacy_value(field)
	return and_(
		user_unblocked_predicate(principal),
		or_(
			User.id == principal.user_id,
			value == Visibility.EVERYONE.value,
			and_(
				value == Visibility.FRIENDS.value,
				accepted_friendship_exists(principal.user_id, User.id),
			),
		),
	)


def user_visibility_predicate(
	principal: Principal,
	include_inactive: bool = False,
) -> ColumnElement[bool]:
	"""return users whose identity may be resolved by the principal."""
	return user_search_candidate_predicate(
		principal,
		include_inactive=include_inactive,
	)


def user_username_filter_predicate(principal: Principal) -> ColumnElement[bool]:
	"""return whether username may be queried for a user."""
	return user_search_candidate_predicate(principal)


def user_display_name_filter_predicate(principal: Principal) -> ColumnElement[bool]:
	"""return whether display name may be queried for a user."""
	return and_(
		user_search_candidate_predicate(principal),
		user_privacy_visibility_predicate(principal, "real_name"),
	)


def user_bio_filter_predicate(principal: Principal) -> ColumnElement[bool]:
	"""return whether public bio may be queried for a user."""
	return and_(
		user_search_candidate_predicate(principal),
		user_privacy_visibility_predicate(principal, "bio"),
	)


def user_email_filter_predicate(principal: Principal) -> ColumnElement[bool]:
	"""return whether email may be queried for a user."""
	if principal.is_admin:
		return true()
	return and_(
		user_search_candidate_predicate(principal),
		User.find_by_email.is_(True),
	)
