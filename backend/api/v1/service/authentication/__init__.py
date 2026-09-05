"""authentication service facade."""

from api.v1.service.authentication.identity import (
	authenticate_user,
	get_current_active_user,
	get_current_user,
	get_optional_user,
)
from api.v1.service.authentication.principals import (
	Principal,
	PrincipalKindError,
	build_principal,
	build_principals,
	get_current_principal,
	get_optional_principal,
	load_principal_for_user,
)
from api.v1.service.authentication.tokens import (
	create_access_token,
	create_refresh_token,
	create_token_pair,
	refresh_token_for_user,
	revoke_session_from_token,
)
from api.v1.service.authentication.web import (
	REFRESH_COOKIE_NAME,
	authenticate_websocket_refresh_cookie,
	is_websocket_origin_allowed,
	origin_allowed,
	require_csrf_origin,
)


__all__ = [
	"REFRESH_COOKIE_NAME",
	"Principal",
	"PrincipalKindError",
	"authenticate_user",
	"authenticate_websocket_refresh_cookie",
	"build_principal",
	"build_principals",
	"create_access_token",
	"create_refresh_token",
	"create_token_pair",
	"get_current_active_user",
	"get_current_principal",
	"get_current_user",
	"get_optional_principal",
	"get_optional_user",
	"is_websocket_origin_allowed",
	"load_principal_for_user",
	"origin_allowed",
	"refresh_token_for_user",
	"require_csrf_origin",
	"revoke_session_from_token",
]
