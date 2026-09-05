"""shared object factories for api tests."""

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.permissions import PermissionGrant
from api.v1.schemas.auth import UserSubject
from api.v1.service.authentication import Principal
from api.v1.service.threads.content_vectors import reconcile_thread_content_vectors
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID, new_typeid


async def reconcile_one_thread(
	thread_id: TypeID, db_session: AsyncSession
) -> JSONObject:
	"""reconcile a single thread's content vectors and return its summary."""
	summaries = await reconcile_thread_content_vectors(
		db_session, thread_ids=[thread_id]
	)
	return summaries[0]


async def create_user(
	db_session: AsyncSession, slug: str, is_superuser: bool = False
) -> User:
	"""persist a user row directly, bypassing service-level bootstrap gates."""
	user = User(
		email=f"{slug}@example.com",
		username=slug,
		hashed_password="x",
		is_active=True,
		is_superuser=is_superuser,
	)
	db_session.add(user)
	await db_session.flush()
	return user


def principal_for(user: User) -> Principal:
	"""bare principal for a persisted user: no groups, roles, or permissions."""
	return Principal.for_user(user=user, group_ids=(), permissions=frozenset())


def make_principal(
	slug: str | None = None,
	is_superuser: bool = False,
	permissions: frozenset[PermissionGrant] = frozenset(),
	group_ids: tuple[TypeID, ...] = (),
	global_action_permissions: frozenset[PermissionGrant] = frozenset(),
) -> Principal:
	"""standalone principal with no backing user row (subject built directly)."""
	user_id = TypeID(new_typeid("user"))
	name = slug or f"p{str(user_id)[-12:]}"
	subject = UserSubject(
		id=user_id,
		email=f"{name}@example.com",
		username=name,
		is_superuser=is_superuser,
	)
	return Principal(
		subject=subject,
		group_ids=group_ids,
		permissions=permissions,
		global_action_permissions=global_action_permissions,
	)
