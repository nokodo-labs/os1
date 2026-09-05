"""agent run thread context resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent as AgentORM
from api.schemas.common import MISSING, unwrap_missing
from api.schemas.runs import ClientContext
from api.v1.service.authentication import Principal
from api.v1.service.chat.messages import inject_system_instructions, load_sdk_thread
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.sentinels import MissingType
from nokodo_ai.utils.typeid import TypeID


async def resolve_run_thread(
	agent: AgentORM,
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID | None,
	initial_parent_id: TypeID | None | MissingType,
	resolved_input_message: SDKUserMessage | None,
	client_context: ClientContext | None,
	persist: bool,
) -> tuple[SDKThread, TypeID | None]:
	"""resolve the SDKThread and head id used to seed the agent run.

	unifies the persist and ephemeral paths:

	- persist=True: load the thread from the DB starting at ``initial_parent_id``,
		inject system instructions, return the thread + the resolved head id
		(which becomes ``initial_parent_id`` for downstream message persistence).
	- persist=False with thread_id: load the thread for context only, append
		any ephemeral user input, inject system instructions, return.
	- persist=False without thread_id: synthesize a thread from the resolved
		input alone.

	returns ``(thread, head_id)``. ``head_id`` is non-None only when persisting.
	"""
	if persist:
		assert thread_id is not None  # persist=True requires a thread_id
		sdk_thread, head_id = await load_sdk_thread(
			thread_id,
			session,
			principal=principal,
			parent_id=initial_parent_id,
		)
		if initial_parent_id is MISSING:
			resolved_head = head_id
		else:
			resolved_head = unwrap_missing(initial_parent_id)
		thread = await inject_system_instructions(
			agent,
			sdk_thread,
			session=session,
			principal=principal,
			client_context=client_context,
		)
		return thread, resolved_head

	# ephemeral: no persistence; load thread context if thread_id provided
	if thread_id is not None:
		sdk_thread, _ = await load_sdk_thread(
			thread_id,
			session,
			principal=principal,
			parent_id=initial_parent_id,
		)
	else:
		sdk_thread = SDKThread(messages=[])

	if resolved_input_message is not None:
		sdk_thread = sdk_thread.model_copy(
			update={
				"messages": [
					*sdk_thread.messages,
					resolved_input_message,
				]
			}
		)

	thread = await inject_system_instructions(
		agent,
		sdk_thread,
		session=session,
		principal=principal,
		client_context=client_context,
	)

	return thread, None
