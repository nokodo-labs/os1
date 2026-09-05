"""tests for steering inbox and drain logic on RunStore."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import MessageType
from api.permissions import MentionableSubjectType
from api.schemas.message import (
	Citation,
	CitationSource,
	MessageCreate,
	MessageMention,
	TextContent,
)
from api.tests.factories import make_principal
from api.v1.service.authentication import Principal
from api.v1.service.chat.message_metadata import (
	ATTACHMENTS_KEY,
	CITATIONS_KEY,
	CLIENT_STEERING_ID_KEY,
	FOLDED_METADATA_KEYS,
	persisted_message_metadata,
	to_persisted_metadata,
)
from api.v1.service.chat.messages import prepare_generated_message
from api.v1.service.runs import resolution as run_resolution
from api.v1.service.runs import steering as steering_service
from api.v1.service.runs.bus import RunRoute
from api.v1.service.runs.status import (
	_MAX_INBOX,
	RunStore,
	run_inbox,
	run_registry,
)
from api.v1.service.runs.steering import InvocationCatchUp, QueuedSteering
from api.v1.service.runs.steering_bus import (
	CancelRunCommand,
	DropSteeringCommand,
	EnqueueSteeringCommand,
	InvocationSteeringCommand,
	publish_steering_command,
	start_steering_subscriber,
)
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import TextContent as SDKTextContent
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _queued(message_id: str, text: str = "steer") -> QueuedSteering:
	"""a user steering message: persisted as a ghost row, so retractable."""
	return QueuedSteering(
		message_id=TypeID(message_id),
		message=SDKUserMessage(content=[SDKTextContent(text=text)]),
	)


def _catch_up(message_id: str) -> InvocationCatchUp:
	"""a server-owned catch-up: writes nothing, so it is not retractable."""
	return InvocationCatchUp(
		message_id=TypeID(message_id),
		messages=[SDKUserMessage(content=[SDKTextContent(text="@agent")])],
	)


@pytest.mark.asyncio
async def test_enqueue_steering_when_running_accepts_message() -> None:
	"""enqueue_steering returns True and queues for a running run."""
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s1"),
		thread_id=TypeID("thread_s1"),
		agent_id=TypeID("agent_s1"),
		user_id=TypeID("user_s1"),
	)
	accepted = await store.enqueue(TypeID("run_s1"), _queued("msg_s1"))
	assert accepted is True
	rs = await store.get_run(TypeID("run_s1"))
	assert rs is not None
	assert list(rs.in_flight_steering) == ["msg_s1"]
	assert len(rs.inbox_message_ids) == 1


@pytest.mark.asyncio
async def test_non_persisted_run_rejects_text_steering_before_write(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	principal = make_principal(slug="ephemeral-steering")
	create = AsyncMock()
	monkeypatch.setattr(steering_service, "create_message", create)
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		principal.user.id,
		thread_id,
		persist=False,
	)
	try:
		with pytest.raises(HTTPException) as error:
			await steering_service.enqueue_run_steering(
				run_id,
				MessageCreate(content=[TextContent(text="no")]),
				None,
				None,
				principal,
				AsyncMock(spec=AsyncSession),
			)
		assert error.value.status_code == 409
		create.assert_not_awaited()
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_redis_steering_command_reaches_owner() -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	received = asyncio.Event()

	async def handle(command: object) -> None:
		assert isinstance(command, EnqueueSteeringCommand)
		assert command.message_id == message_id
		assert command.thread_id == thread_id
		assert command.agent_id == agent_id
		received.set()

	subscriber = await start_steering_subscriber(run_id, handle)
	try:
		command = EnqueueSteeringCommand(
			message_id=message_id,
			messages=[SDKUserMessage.from_text("remote steer")],
			retractable=True,
			thread_id=thread_id,
			agent_id=agent_id,
		)
		for _attempt in range(3):
			delivered = await publish_steering_command(run_id, command)
			if delivered:
				break
			await asyncio.sleep(0)
		assert delivered > 0
		await asyncio.wait_for(received.wait(), timeout=1)
	finally:
		subscriber.cancel()


@pytest.mark.asyncio
async def test_enqueue_run_steering_accepts_before_subscriber_starts(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a locally registered run accepts steering before redis subscriber startup."""
	run_id = TypeID("run_direct_steer")
	thread_id = TypeID("thread_direct_steer")
	agent_id = TypeID("agent_direct_steer")
	principal = make_principal(slug="early-steer")
	user_id = principal.user.id
	message_id = TypeID("msg_direct_steer")
	persisted_message_id = message_id

	async def fake_enabled(_agent_id: TypeID, _db: object) -> bool:
		return True

	async def fake_require_access(*_args: object, **_kwargs: object) -> None:
		return None

	async def fake_create_message(
		thread_id: TypeID,
		draft: object,
		session: object,
		principal: Principal,
		**kwargs: object,
	) -> object:
		assert session is not None
		assert thread_id is not None
		assert principal.user.id == user_id
		assert isinstance(draft, steering_service.MessageDraft)
		assert draft.content == [TextContent(text="early steer")]
		assert draft.metadata[CLIENT_STEERING_ID_KEY] == "local-steering-1"
		assert draft.metadata["steering_state"] == "queued"
		assert draft.metadata["run_id"] == "run_direct_steer"
		assert kwargs["origin_session_id"] is None
		# a queued message is not conversation yet, so the write must not move
		# the thread head.
		assert kwargs["advances_head"] is False

		class _FakePersistedMessage:
			id = persisted_message_id
			created_at = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
			attachments: list[dict[str, object]] = []

			def to_sdk(self) -> SDKUserMessage:
				return SDKUserMessage(content=[SDKTextContent(text="early steer")])

		message = SimpleNamespace(
			id=_FakePersistedMessage.id,
			created_at=_FakePersistedMessage.created_at,
			attachments=_FakePersistedMessage.attachments,
			to_sdk=_FakePersistedMessage().to_sdk,
		)
		return SimpleNamespace(message=message)

	monkeypatch.setattr(steering_service, "_is_steering_enabled", fake_enabled)
	monkeypatch.setattr(run_resolution, "require_thread_access", fake_require_access)
	monkeypatch.setattr(steering_service, "create_message", fake_create_message)
	# prevent fire-and-forget broadcast tasks from outliving the test
	monkeypatch.setattr(
		steering_service, "create_background_task", lambda coro, name: coro.close()
	)

	await run_registry.start_run(run_id, agent_id, user_id, thread_id)
	try:
		db = AsyncMock(spec=AsyncSession)
		db.get.return_value = SimpleNamespace(current_message_id=None)
		result = await steering_service.enqueue_run_steering(
			run_id,
			MessageCreate(content=[TextContent(text="early steer")]),
			None,
			"local-steering-1",
			principal,
			db,
		)

		assert result.state == "queued"
		assert result.message_id == message_id
		drained = await run_inbox.claim_inbox(run_id)
		assert len(drained) == 1
		queued = drained[0].messages[0]
		assert queued.metadata is not None
		assert queued.metadata[CLIENT_STEERING_ID_KEY] == "local-steering-1"
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_remote_text_steering_routes_to_owner(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="remote-text-steering")
	route = RunRoute(
		thread_id=thread_id,
		container_root_id=None,
		agent_id=agent_id,
		user_id=principal.user.id,
		persist=True,
	)
	publish = AsyncMock(return_value=1)
	monkeypatch.setattr(run_resolution, "read_run_route", AsyncMock(return_value=route))
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	monkeypatch.setattr(
		steering_service, "_is_steering_enabled", AsyncMock(return_value=True)
	)
	monkeypatch.setattr(steering_service, "publish_steering_command", publish)
	monkeypatch.setattr(
		steering_service, "create_background_task", lambda coro, name: coro.close()
	)

	class _Persisted:
		id = message_id
		created_at = datetime.now(tz=UTC)
		attachments: list[dict[str, object]] = []

		def to_sdk(self) -> SDKUserMessage:
			return SDKUserMessage.from_text("remote steer")

	monkeypatch.setattr(
		steering_service,
		"create_message",
		AsyncMock(return_value=SimpleNamespace(message=_Persisted())),
	)

	result = await steering_service.enqueue_run_steering(
		run_id,
		MessageCreate(content="remote steer"),
		None,
		None,
		principal,
		AsyncMock(spec=AsyncSession),
	)

	assert result.state == "queued"
	command = publish.await_args.args[1]
	assert isinstance(command, EnqueueSteeringCommand)
	assert command.message_id == message_id
	assert command.thread_id == thread_id
	assert command.agent_id == agent_id


@pytest.mark.asyncio
async def test_remote_invocation_routes_to_owner(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="remote-invocation-steering")
	route = RunRoute(
		thread_id=thread_id,
		container_root_id=None,
		agent_id=agent_id,
		user_id=principal.user.id,
		persist=True,
	)
	publish = AsyncMock(return_value=1)
	monkeypatch.setattr(run_resolution, "read_run_route", AsyncMock(return_value=route))
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	monkeypatch.setattr(
		steering_service, "message_mentions_agent", AsyncMock(return_value=True)
	)
	monkeypatch.setattr(
		steering_service, "branch_root_id", AsyncMock(return_value=None)
	)
	monkeypatch.setattr(steering_service, "publish_steering_command", publish)

	result = await steering_service.enqueue_run_invocation(
		run_id,
		message_id,
		principal,
		AsyncMock(spec=AsyncSession),
	)

	assert result.state == "queued"
	command = publish.await_args.args[1]
	assert isinstance(command, InvocationSteeringCommand)
	assert command.message_id == message_id
	assert command.thread_id == thread_id
	assert command.agent_id == agent_id


@pytest.mark.asyncio
async def test_remote_drop_routes_to_owner(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="remote-drop-steering")
	route = RunRoute(
		thread_id=thread_id,
		container_root_id=None,
		agent_id=agent_id,
		user_id=principal.user.id,
		persist=True,
	)
	publish = AsyncMock(return_value=1)
	monkeypatch.setattr(run_resolution, "read_run_route", AsyncMock(return_value=route))
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	monkeypatch.setattr(steering_service, "publish_steering_command", publish)
	stored_message = SimpleNamespace(
		thread_id=thread_id,
		public_metadata={"run_id": str(run_id)},
	)
	db = AsyncMock(spec=AsyncSession)
	db.get.return_value = stored_message

	await steering_service.drop_run_steering(
		run_id,
		message_id,
		principal,
		db,
	)

	command = publish.await_args.args[1]
	assert isinstance(command, DropSteeringCommand)
	assert command.message_id == message_id
	assert command.thread_id == thread_id
	assert command.agent_id == agent_id


@pytest.mark.asyncio
async def test_remote_drop_rejects_message_from_another_thread(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="foreign-drop")
	route = RunRoute(
		thread_id=thread_id,
		container_root_id=None,
		agent_id=TypeID(new_typeid("agent")),
		user_id=principal.user.id,
		persist=True,
	)
	foreign = SimpleNamespace(
		thread_id=TypeID(new_typeid("thread")),
		public_metadata={"run_id": str(run_id)},
	)
	db = AsyncMock(spec=AsyncSession)
	db.get.return_value = foreign
	monkeypatch.setattr(run_resolution, "read_run_route", AsyncMock(return_value=route))

	with pytest.raises(HTTPException) as raised:
		await steering_service.drop_run_steering(
			run_id,
			message_id,
			principal,
			db,
		)
	assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_remote_drop_without_owner_leaves_message_queued(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="unreachable-drop")
	route = RunRoute(
		thread_id=thread_id,
		container_root_id=None,
		agent_id=TypeID(new_typeid("agent")),
		user_id=principal.user.id,
		persist=True,
	)
	stored = SimpleNamespace(
		thread_id=thread_id,
		public_metadata={"run_id": str(run_id)},
	)
	db = AsyncMock(spec=AsyncSession)
	db.get.return_value = stored
	monkeypatch.setattr(run_resolution, "read_run_route", AsyncMock(return_value=route))
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	monkeypatch.setattr(
		steering_service,
		"publish_steering_command",
		AsyncMock(return_value=0),
	)

	with pytest.raises(HTTPException) as raised:
		await steering_service.drop_run_steering(
			run_id,
			message_id,
			principal,
			db,
		)
	assert raised.value.status_code == 409


@pytest.mark.asyncio
async def test_remote_cancel_routes_to_owner(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import runs as runs_router

	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	principal = make_principal(slug="remote-cancel")
	route = RunRoute(
		thread_id=thread_id,
		container_root_id=None,
		agent_id=TypeID(new_typeid("agent")),
		user_id=principal.user.id,
		persist=True,
	)
	publish = AsyncMock(return_value=1)
	monkeypatch.setattr(run_resolution, "read_run_route", AsyncMock(return_value=route))
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	monkeypatch.setattr(runs_router, "publish_steering_command", publish)

	result = await runs_router.cancel_run(
		run_id,
		principal,
		AsyncMock(spec=AsyncSession),
	)

	assert result == {"status": "cancelled"}
	command = publish.await_args.args[1]
	assert isinstance(command, CancelRunCommand)
	assert command.reason == "cancelled"


@pytest.mark.asyncio
async def test_text_steering_rejects_other_agent_before_persistence(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	other_agent_id = TypeID(new_typeid("agent"))
	principal = make_principal(slug="steering-mention")
	persisted = False

	async def fake_enabled(_agent_id: TypeID, _db: object) -> bool:
		return True

	async def fake_require_access(*_args: object, **_kwargs: object) -> None:
		return None

	async def fake_create_message(*_args: object, **_kwargs: object) -> object:
		nonlocal persisted
		persisted = True
		return object()

	monkeypatch.setattr(steering_service, "_is_steering_enabled", fake_enabled)
	monkeypatch.setattr(run_resolution, "require_thread_access", fake_require_access)
	monkeypatch.setattr(
		steering_service,
		"create_message",
		fake_create_message,
	)
	await run_registry.start_run(
		run_id,
		agent_id,
		principal.user.id,
		thread_id,
	)
	try:
		with pytest.raises(HTTPException) as invalid:
			await steering_service.enqueue_run_steering(
				run_id,
				MessageCreate(
					content="@agent continue",
					mentions=[
						MessageMention(
							type=MentionableSubjectType.AGENT,
							id=other_agent_id,
						)
					],
				),
				None,
				None,
				principal,
				AsyncMock(spec=AsyncSession),
			)
		assert invalid.value.status_code == 501
		assert not persisted
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", [MessageType.ASSISTANT, MessageType.SYSTEM])
async def test_text_steering_rejects_non_user_before_persistence(
	monkeypatch: pytest.MonkeyPatch,
	message_type: MessageType,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	principal = make_principal(slug=f"steering-{message_type.value}")
	create = AsyncMock()
	monkeypatch.setattr(steering_service, "create_message", create)
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	monkeypatch.setattr(
		steering_service, "_is_steering_enabled", AsyncMock(return_value=True)
	)
	await run_registry.start_run(run_id, agent_id, principal.user.id, thread_id)
	try:
		with pytest.raises(HTTPException) as invalid:
			await steering_service.enqueue_run_steering(
				run_id,
				MessageCreate(type=message_type, content="no"),
				None,
				None,
				principal,
				AsyncMock(spec=AsyncSession),
			)
		assert invalid.value.status_code == 422
		create.assert_not_awaited()
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_text_steering_rejects_input_splice_before_persistence(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	principal = make_principal(slug="steering-splice")
	create = AsyncMock()
	monkeypatch.setattr(steering_service, "create_message", create)
	monkeypatch.setattr(run_resolution, "require_thread_access", AsyncMock())
	monkeypatch.setattr(
		steering_service, "_is_steering_enabled", AsyncMock(return_value=True)
	)
	await run_registry.start_run(run_id, agent_id, principal.user.id, thread_id)
	try:
		with pytest.raises(HTTPException) as invalid:
			await steering_service.enqueue_run_steering(
				run_id,
				MessageCreate(
					content="no",
					splice=steering_service.MessageSplice(parent_id=None),
				),
				None,
				None,
				principal,
				AsyncMock(spec=AsyncSession),
			)
		assert invalid.value.status_code == 422
		create.assert_not_awaited()
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("subject_type", "same_agent"),
	[
		(MentionableSubjectType.AGENT, True),
		(MentionableSubjectType.USER, False),
		(MentionableSubjectType.GROUP, False),
	],
)
async def test_text_steering_allows_noninvoking_mentions(
	monkeypatch: pytest.MonkeyPatch,
	subject_type: MentionableSubjectType,
	same_agent: bool,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	principal = make_principal(slug=f"steering-{subject_type.value}")

	async def fake_enabled(_agent_id: TypeID, _db: object) -> bool:
		return True

	async def fake_require_access(*_args: object, **_kwargs: object) -> None:
		return None

	async def fake_create_message(
		_thread_id: TypeID,
		draft: object,
		_db: object,
		_principal: Principal,
		**_kwargs: object,
	) -> object:
		assert isinstance(draft, steering_service.MessageDraft)

		class _Persisted:
			id = TypeID(new_typeid("msg"))
			created_at = datetime.now(tz=UTC)
			attachments: list[dict[str, object]] = []

			def to_sdk(self) -> SDKUserMessage:
				return SDKUserMessage(content=[SDKTextContent(text="steer")])

		return SimpleNamespace(message=_Persisted())

	monkeypatch.setattr(steering_service, "_is_steering_enabled", fake_enabled)
	monkeypatch.setattr(run_resolution, "require_thread_access", fake_require_access)
	monkeypatch.setattr(
		steering_service,
		"create_message",
		fake_create_message,
	)
	monkeypatch.setattr(
		steering_service, "create_background_task", lambda coro, name: coro.close()
	)
	await run_registry.start_run(run_id, agent_id, principal.user.id, thread_id)
	try:
		result = await steering_service.enqueue_run_steering(
			run_id,
			MessageCreate(
				content="steer",
				mentions=[
					MessageMention(
						type=subject_type,
						id=(
							agent_id
							if same_agent
							else TypeID(new_typeid(subject_type.value))
						),
					)
				],
			),
			None,
			None,
			principal,
			AsyncMock(spec=AsyncSession),
		)
		assert result.state == "queued"
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_enqueue_steering_unknown_run_returns_false() -> None:
	store = RunStore()
	assert await store.enqueue(TypeID("run_nope"), _queued("msg_x")) is False


@pytest.mark.asyncio
async def test_enqueue_steering_terminal_run_returns_false() -> None:
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s2"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.complete_run(TypeID("run_s2"))
	assert await store.enqueue(TypeID("run_s2"), _queued("m")) is False


@pytest.mark.asyncio
async def test_enqueue_steering_full_inbox_returns_false() -> None:
	"""inbox is bounded; once full further enqueues fail without blocking."""
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s3"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	for i in range(_MAX_INBOX):
		assert await store.enqueue(TypeID("run_s3"), _queued(f"msg_{i}")) is True
	assert await store.enqueue(TypeID("run_s3"), _queued("overflow")) is False


@pytest.mark.asyncio
async def test_claim_pending_steering_drains_and_moves_to_claimed() -> None:
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s4"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.enqueue(TypeID("run_s4"), _queued("m1"))
	await store.enqueue(TypeID("run_s4"), _queued("m2"))
	drained = await store.claim_inbox(TypeID("run_s4"))
	assert [injection.message_id for injection in drained] == ["m1", "m2"]
	rs = await store.get_run(TypeID("run_s4"))
	assert rs is not None
	assert list(rs.claimed_steering) == ["m1", "m2"]
	assert rs.inbox_message_ids == ()
	# in-flight surfaces both pending and claimed for terminal handlers
	assert list(rs.in_flight_steering) == ["m1", "m2"]
	# idempotent
	assert await store.claim_inbox(TypeID("run_s4")) == []


@pytest.mark.asyncio
async def test_claim_pending_steering_unknown_run_returns_empty() -> None:
	store = RunStore()
	assert await store.claim_inbox(TypeID("run_nope")) == []


@pytest.mark.asyncio
async def test_has_in_flight_steering_tracks_pending_and_claimed() -> None:
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s8"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	assert await store.has_in_flight_steering(TypeID("run_s8")) is False
	await store.enqueue(TypeID("run_s8"), _queued("m1"))
	assert await store.has_in_flight_steering(TypeID("run_s8")) is True
	await store.claim_inbox(TypeID("run_s8"))
	assert await store.has_in_flight_steering(TypeID("run_s8")) is True
	await store.mark_steering_injected(TypeID("run_s8"), [TypeID("m1")])
	assert await store.has_in_flight_steering(TypeID("run_s8")) is False


@pytest.mark.asyncio
async def test_mark_steering_injected_removes_only_listed_ids() -> None:
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s5"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.enqueue(TypeID("run_s5"), _queued("m1"))
	await store.enqueue(TypeID("run_s5"), _queued("m2"))
	await store.enqueue(TypeID("run_s5"), _queued("m3"))
	# the filter claims the batch, then confirms part of it: only what it
	# confirmed stops owing a resolution.
	await store.claim_inbox(TypeID("run_s5"))
	await store.mark_steering_injected(TypeID("run_s5"), [TypeID("m1"), TypeID("m3")])
	rs = await store.get_run(TypeID("run_s5"))
	assert rs is not None
	assert list(rs.in_flight_steering) == ["m2"]


@pytest.mark.asyncio
async def test_mark_steering_injected_empty_or_unknown_run_is_noop() -> None:
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s6"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.enqueue(TypeID("run_s6"), _queued("m1"))
	await store.mark_steering_injected(TypeID("run_s6"), [])
	rs = await store.get_run(TypeID("run_s6"))
	assert rs is not None
	assert list(rs.in_flight_steering) == ["m1"]
	# unknown run does not raise
	await store.mark_steering_injected(TypeID("run_unknown"), [TypeID("m1")])


@pytest.mark.asyncio
async def test_steering_inbox_is_bounded_at_64_by_default() -> None:
	"""sanity: the inbox is bounded so a misbehaving client cannot OOM."""
	store = RunStore()
	await store.start_run(
		run_id=TypeID("run_s7"),
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	assert _MAX_INBOX > 0
	# must not block: appending under the lock either accepts or refuses,
	# never awaits indefinitely. attempting cap+5 enqueues completes immediately.
	for i in range(_MAX_INBOX + 5):
		await asyncio.wait_for(
			store.enqueue(TypeID("run_s7"), _queued(f"m{i}")), timeout=1.0
		)
	rs = await store.get_run(TypeID("run_s7"))
	assert rs is not None
	assert len(rs.inbox_message_ids) == _MAX_INBOX


@pytest.mark.asyncio
async def test_catch_up_is_not_in_flight_steering() -> None:
	"""a catch-up owes the user no retraction: it never wrote a ghost row.

	it shares the inbox with queued steering, but only queued steering is
	persisted before the agent reads it, so only queued steering can be left
	owing a `dropped` resolution when the run dies.
	"""
	store = RunStore()
	run_id = TypeID("run_mixed")
	await store.start_run(
		run_id=run_id,
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	await store.enqueue(run_id, _queued("msg_typed"))
	await store.enqueue(run_id, _catch_up("msg_mention"))

	rs = await store.get_run(run_id)
	assert rs is not None
	assert len(rs.inbox_message_ids) == 2
	assert list(rs.in_flight_steering) == ["msg_typed"]

	# and it stays out of the registry across a claim, so a run that dies
	# mid-catch-up does not broadcast a drop for the user's own mention.
	await store.claim_inbox(run_id)
	rs = await store.get_run(run_id)
	assert rs is not None
	assert list(rs.in_flight_steering) == ["msg_typed"]


@pytest.mark.asyncio
async def test_drop_pending_steering_cannot_cancel_a_catch_up() -> None:
	"""DELETE /steer/{id} retracts a user's own message, not a server catch-up."""
	store = RunStore()
	run_id = TypeID("run_drop_scope")
	await store.start_run(
		run_id=run_id,
		thread_id=TypeID("t"),
		agent_id=TypeID("a"),
		user_id=TypeID("u"),
	)
	catch_up_id = TypeID("msg_mention")
	await store.enqueue(run_id, _catch_up(str(catch_up_id)))

	assert await store.drop_pending_steering(run_id, catch_up_id) is False
	rs = await store.get_run(run_id)
	assert rs is not None
	assert len(rs.inbox_message_ids) == 1


@pytest.mark.asyncio
async def test_drop_removes_from_inbox_before_settling(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID("run_drop_order")
	thread_id = TypeID("thread_drop_order")
	message_id = TypeID("msg_drop_order")
	principal = make_principal(slug="drop-order")
	await run_registry.start_run(
		run_id=run_id,
		thread_id=thread_id,
		agent_id=TypeID("agent_drop_order"),
		user_id=principal.user.id,
	)
	await run_inbox.enqueue(run_id, _queued(str(message_id)))
	settled = asyncio.Event()
	order: list[str] = []

	async def allow(*_args: object, **_kwargs: object) -> None:
		return None

	async def capture_settle(*_args: object, **_kwargs: object) -> None:
		order.append("settle")
		settled.set()

	original_drop = run_inbox.drop_pending_steering

	async def contended_drop(
		target_run_id: TypeID,
		target_message_id: TypeID,
	) -> bool:
		await asyncio.sleep(0)
		assert not settled.is_set()
		removed = await original_drop(target_run_id, target_message_id)
		order.append("remove")
		return removed

	monkeypatch.setattr(run_resolution, "require_thread_access", allow)
	monkeypatch.setattr(steering_service, "_settle_drop", capture_settle)
	monkeypatch.setattr(
		run_inbox,
		"drop_pending_steering",
		contended_drop,
	)
	stored_message = SimpleNamespace(
		thread_id=thread_id,
		public_metadata={"run_id": str(run_id)},
	)
	db = AsyncMock(spec=AsyncSession)
	db.get.return_value = stored_message
	try:
		await steering_service.drop_run_steering(
			run_id,
			message_id,
			principal,
			db,
		)
		await asyncio.wait_for(settled.wait(), timeout=1)
		assert order == ["remove", "settle"]
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_rebinding_does_not_rewind_catch_up_cursors() -> None:
	store = RunStore()
	run_id = TypeID("run_bind_once")
	first = TypeID("msg_first")
	newer = TypeID("msg_newer")
	await store.start_run(
		run_id,
		thread_id=TypeID("thread_bind_once"),
		agent_id=TypeID("agent_bind_once"),
		user_id=TypeID("user_bind_once"),
	)
	await store.bind(run_id, None, first)
	await store.reserve_catch_up(run_id, newer)
	await store.mark_catch_up_injected(run_id, newer)
	await store.bind(run_id, None, None, first)
	rs = await store.get_run(run_id)
	assert rs is not None
	assert rs.queued_through_message_id == newer
	assert rs.injected_through_message_id == newer


@pytest.mark.asyncio
async def test_regeneration_binds_its_boundary_and_anchor_together() -> None:
	"""a run announced with no boundary would accept the whole branch as
	"catch-up", so binding settles both before anyone can reach the run."""
	store = RunStore()
	run_id = TypeID("run_resolved_boundary")
	head = TypeID("msg_resolved_boundary")
	await store.start_run(
		run_id,
		thread_id=TypeID("thread_resolved_boundary"),
		agent_id=TypeID("agent_resolved_boundary"),
		user_id=TypeID("user_resolved_boundary"),
	)
	await store.bind(run_id, None, None, read_through_message_id=head)
	rs = await store.get_run(run_id)
	assert rs is not None
	assert rs.queued_through_message_id == head
	assert rs.injected_through_message_id == head
	assert rs.anchor_message_id == head


@pytest.mark.asyncio
async def test_bind_anchors_a_run_that_reads_from_nothing() -> None:
	"""regenerating from an empty conversation still renders somewhere."""
	store = RunStore()
	run_id = TypeID("run_empty_boundary")
	head = TypeID("msg_empty_boundary")
	await store.start_run(
		run_id,
		thread_id=TypeID("thread_empty_boundary"),
		agent_id=TypeID("agent_empty_boundary"),
		user_id=TypeID("user_empty_boundary"),
	)
	await store.bind(run_id, None, None, anchor_message_id=head)
	rs = await store.get_run(run_id)
	assert rs is not None
	assert rs.injected_through_message_id is None
	assert rs.anchor_message_id == head


@pytest.mark.asyncio
async def test_touch_run_updates_heartbeat_without_a_frame() -> None:
	store = RunStore()
	run_id = TypeID("run_heartbeat")
	await store.start_run(
		run_id,
		thread_id=None,
		agent_id=TypeID("agent_heartbeat"),
		user_id=TypeID("user_heartbeat"),
	)
	rs = await store.get_run(run_id)
	assert rs is not None
	before = rs.updated_at
	await asyncio.sleep(0)
	await store.touch_run(run_id)
	after = await store.get_run(run_id)
	assert after is not None
	assert after.updated_at > before
	# a heartbeat is not a frame: nothing was published, so there is no catchup.
	subscription = await store.subscribe(run_id, TypeID(new_typeid("user")))
	assert subscription is not None
	catchup, queue = subscription
	assert catchup == []
	await store.unsubscribe(run_id, queue)


@pytest.mark.asyncio
async def test_mirror_drain_keeps_frame_enqueued_during_flush(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import status as run_status_module

	store = RunStore()
	run_id = TypeID(new_typeid("run"))
	await store.start_run(
		run_id,
		thread_id=None,
		agent_id=TypeID(new_typeid("agent")),
		user_id=TypeID(new_typeid("user")),
	)
	first_started = asyncio.Event()
	release_first = asyncio.Event()
	batches: list[list[bytes]] = []

	async def mirror(_run_id: TypeID, frames: list[bytes]) -> None:
		batches.append(frames)
		if len(batches) == 1:
			first_started.set()
			await release_first.wait()

	monkeypatch.setattr(run_status_module, "mirror_frames", mirror)
	await store.publish(run_id, b"first")
	await first_started.wait()
	await store.publish(run_id, b"second")
	release_first.set()
	await store._flush_mirrors(run_id)

	assert batches == [[b"first"], [b"second"]]


@pytest.mark.asyncio
async def test_mirror_flush_failure_is_bounded_and_cleans_task(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import status as run_status_module

	store = RunStore()
	run_id = TypeID(new_typeid("run"))
	await store.start_run(
		run_id,
		thread_id=None,
		agent_id=TypeID(new_typeid("agent")),
		user_id=TypeID(new_typeid("user")),
	)

	async def fail(*_args: object, **_kwargs: object) -> None:
		raise RuntimeError("mirror failed")

	monkeypatch.setattr(run_status_module, "mirror_frames", fail)
	await store.publish(run_id, b"frame")
	await store._flush_mirrors(run_id)
	assert run_id not in store._mirror_tasks
	assert run_id not in store._mirror_queues


@pytest.mark.asyncio
async def test_slow_subscriber_receives_truncated_before_done() -> None:
	store = RunStore()
	run_id = TypeID(new_typeid("run"))
	await store.start_run(
		run_id,
		thread_id=None,
		agent_id=TypeID(new_typeid("agent")),
		user_id=TypeID(new_typeid("user")),
	)
	result = await store.subscribe(run_id, TypeID(new_typeid("user")))
	assert result is not None
	_catchup, queue = result
	for _index in range(queue.maxsize):
		queue.put_nowait(b"full")

	await store.publish(run_id, b"overflow")

	truncated = await queue.get()
	assert truncated is not None
	assert truncated.startswith(b"event: truncated")
	assert await queue.get() is None


@pytest.mark.asyncio
async def test_local_catchup_marks_truncated_history(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import status as run_status_module

	store = RunStore()
	run_id = TypeID(new_typeid("run"))
	await store.start_run(
		run_id,
		thread_id=None,
		agent_id=TypeID(new_typeid("agent")),
		user_id=TypeID(new_typeid("user")),
	)
	# publish past the retained window so the catchup really is truncated.
	monkeypatch.setattr(run_status_module, "RUN_LOG_MAX_FRAMES", 1)
	await store.publish(run_id, b"dropped")
	await store.publish(run_id, b"retained")

	result = await store.subscribe(run_id, TypeID(new_typeid("user")))
	assert result is not None
	catchup, queue = result
	assert catchup[0].startswith(b"event: truncated")
	assert catchup[1] == b"retained"
	await store.unsubscribe(run_id, queue)


@pytest.mark.asyncio
async def test_waiter_timeout_expires_the_slot_on_next_claim(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import status as run_status_module
	from api.v1.service.runs.status import AwaitPendingRun, StartNewRun

	store = RunStore()
	thread_id = TypeID("thread_slot_timeout")
	agent_id = TypeID("agent_slot_timeout")
	claimed = await store.claim(thread_id, agent_id, None)
	assert isinstance(claimed, StartNewRun)
	pending = await store.claim(thread_id, agent_id, None)
	assert isinstance(pending, AwaitPendingRun)
	monkeypatch.setattr(run_status_module, "_SLOT_TIMEOUT_SECONDS", 0.01)
	with pytest.raises(TimeoutError):
		await store.wait(pending.slot)
	reclaimed = await store.claim(thread_id, agent_id, None)
	assert isinstance(reclaimed, StartNewRun)
	assert reclaimed.slot is not claimed.slot
	await store.release(thread_id, agent_id, None, reclaimed.slot, None)


@pytest.mark.asyncio
async def test_agent_slot_arbitrates_across_run_stores() -> None:
	from api.v1.service.runs.status import (
		AwaitPendingRun,
		StartNewRun,
		SteerExistingRun,
	)

	owner = RunStore()
	other = RunStore()
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	run_id = TypeID(new_typeid("run"))
	claim = await owner.claim(thread_id, agent_id, None)
	assert isinstance(claim, StartNewRun)
	pending = await other.claim(thread_id, agent_id, None)
	assert isinstance(pending, AwaitPendingRun)
	await owner.start_run(
		run_id,
		agent_id,
		TypeID(new_typeid("user")),
		thread_id,
	)
	await owner.bind(run_id, container_root_id=None, invocation_message_id=None)
	await owner.release(thread_id, agent_id, None, claim.slot, run_id)
	assert await other.wait(pending.slot) == run_id

	active = await other.claim(thread_id, agent_id, None)
	assert isinstance(active, SteerExistingRun)
	assert active.run_id == run_id
	await owner.complete_run(run_id)
	reclaimed = await other.claim(thread_id, agent_id, None)
	assert isinstance(reclaimed, StartNewRun)
	await other.release(thread_id, agent_id, None, reclaimed.slot, None)


def test_to_persisted_metadata_unfold_contract() -> None:
	"""unfold(fold(col)) == col: fold-injected keys dropped, rest carried."""
	persisted: JSONObject = {
		"run_id": "run_x",
		"steering_state": "queued",
		"client_steering_id": "cs_1",
		"_model_id": "claude",
		"_next_citation_index": 3,
		"_e2b_sandbox_id": "sb_1",
	}
	folded: JSONObject = {
		**persisted,
		**persisted_message_metadata(
			new_typeid("msg"), datetime.now(UTC), new_typeid("user")
		),
		CITATIONS_KEY: [{"index": 1}],
		ATTACHMENTS_KEY: [{"file_id": "f"}],
	}

	recovered = to_persisted_metadata(folded)
	assert recovered == persisted
	assert FOLDED_METADATA_KEYS.isdisjoint(recovered)
	assert to_persisted_metadata(None) == {}
	assert to_persisted_metadata({}) == {}


def test_prepare_generated_message_splits_metadata_and_drops_folded_keys() -> None:
	"""the PIPELINE, not just the helper, must split and unfold correctly.

	two regressions, both invisible to the unit test above.

	first: ``_model_id`` / ``_next_citation_index`` were stamped onto the PUBLIC
	half after the split, re-polluting public metadata with prefixed keys on
	every assistant message and undoing the migration for new rows.

	second: ``to_persisted_metadata`` ran AFTER the split, so five of its six
	folded keys (all `_`-prefixed) were already in the private half, where the
	filter could never see them.
	"""
	sdk = SDKAssistantMessage(
		content=[SDKTextContent(text="hello")],
		metadata={
			"run_id": "ignored",
			"_provider_data": {"anthropic": {"tool_call_id": "t1"}},
			**persisted_message_metadata(
				new_typeid("msg"), datetime.now(UTC), new_typeid("user")
			),
			CITATIONS_KEY: [{"index": 1}],
			ATTACHMENTS_KEY: [],
		},
	)

	draft = prepare_generated_message(
		sdk,
		sender_agent_id=None,
		run_id=TypeID(new_typeid("run")),
		citations=[Citation(index=4, source_type=CitationSource.URL, source_id="u")],
		model_id="claude-x",
	).draft

	# public half: no prefixed keys at all, ever.
	assert not [k for k in draft.metadata if k.startswith("_")]
	assert draft.metadata["run_id"] is not None

	# private half: de-prefixed, and carries the backend-owned stamps.
	private = draft.private_metadata
	assert private["model_id"] == "claude-x"
	assert private["next_citation_index"] == 5
	assert private["provider_data"] == {"anthropic": {"tool_call_id": "t1"}}

	# folded keys reach NEITHER half.
	for key in FOLDED_METADATA_KEYS:
		assert key not in draft.metadata
		assert key.removeprefix("_") not in private
