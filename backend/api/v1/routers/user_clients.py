"""user client routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.notification import (
	NotificationPushSubscription as PushSubscriptionModel,
)
from api.models.user_client import UserClient as UserClientModel
from api.schemas.notification import (
	NotificationPushSubscription,
	NotificationPushSubscriptionCreate,
	NotificationPushSubscriptionDelete,
)
from api.schemas.user_client import (
	UserClient,
	UserClientPatch,
	UserClientPreferences,
	UserClientUpsert,
)
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.events import SessionId
from api.v1.service.notifications import (
	delete_push_subscription as delete_push_subscription_service,
)
from api.v1.service.notifications import (
	list_push_subscriptions as list_push_subscriptions_service,
)
from api.v1.service.notifications import (
	unregister_push_subscription as unregister_push_subscription_service,
)
from api.v1.service.notifications import (
	upsert_push_subscription,
)
from api.v1.service.users import delete_user_client as delete_user_client_service
from api.v1.service.users import list_user_clients as list_user_clients_service
from api.v1.service.users import update_user_client as update_user_client_service
from api.v1.service.users import (
	update_user_client_preferences as update_user_client_preferences_service,
)
from api.v1.service.users import upsert_user_client as upsert_user_client_service
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/{user_id}/clients", tags=["user clients"])


@router.post(
	"",
	response_model=UserClient,
	status_code=status.HTTP_200_OK,
)
async def upsert_user_client(
	user_id: TypeID,
	payload: UserClientUpsert,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> UserClientModel:
	"""register or refresh a user client."""
	return await upsert_user_client_service(user_id, db, principal, payload)


@router.get("", response_model=list[UserClient])
async def list_user_clients(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[UserClientModel]:
	"""return clients for a user."""
	return await list_user_clients_service(user_id, db, principal)


@router.post(
	"/{client_id}/push-subscriptions",
	response_model=NotificationPushSubscription,
	status_code=status.HTTP_201_CREATED,
)
async def register_push_subscription(
	user_id: TypeID,
	client_id: TypeID,
	payload: NotificationPushSubscriptionCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> PushSubscriptionModel:
	"""register or update a user client's web push subscription."""
	return await upsert_push_subscription(
		db,
		principal,
		user_id,
		client_id,
		payload,
	)


@router.get(
	"/{client_id}/push-subscriptions",
	response_model=list[NotificationPushSubscription],
)
async def list_push_subscriptions(
	user_id: TypeID,
	client_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[PushSubscriptionModel]:
	"""return web push subscriptions for a user client."""
	return await list_push_subscriptions_service(
		db,
		principal,
		user_id,
		client_id,
	)


@router.delete("/{client_id}/push-subscriptions", status_code=204)
async def unregister_push_subscription(
	user_id: TypeID,
	client_id: TypeID,
	payload: NotificationPushSubscriptionDelete,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a user client's web push subscription by endpoint."""
	await unregister_push_subscription_service(
		db,
		principal,
		user_id,
		client_id,
		payload,
	)


@router.delete("/{client_id}/push-subscriptions/{subscription_id}", status_code=204)
async def delete_push_subscription(
	user_id: TypeID,
	client_id: TypeID,
	subscription_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a web push subscription."""
	await delete_push_subscription_service(
		user_id,
		client_id,
		subscription_id,
		db,
		principal,
	)


@router.patch("/{client_id}", response_model=UserClient)
async def update_user_client(
	user_id: TypeID,
	client_id: TypeID,
	payload: UserClientPatch,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> UserClientModel:
	"""update a registered user client."""
	return await update_user_client_service(
		user_id,
		client_id,
		db,
		principal,
		payload,
	)


@router.put(
	"/{client_id}/preferences",
	response_model=UserClient,
)
async def update_user_client_preferences(
	user_id: TypeID,
	client_id: TypeID,
	payload: UserClientPreferences,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> UserClientModel:
	"""replace client-specific preference overrides."""
	return await update_user_client_preferences_service(
		user_id,
		client_id,
		db,
		principal,
		payload,
		origin_session_id=x_session_id,
	)


@router.delete("/{client_id}", status_code=204)
async def delete_user_client(
	user_id: TypeID,
	client_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a registered user client."""
	await delete_user_client_service(user_id, client_id, db, principal)
