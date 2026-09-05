"""thread content vectorization task orchestration."""

from taskiq import async_shared_broker

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.settings import settings
from api.v1.service.threads.content_vectors import reconcile_thread_content_vectors
from api.v1.service.threads.search import vectorize_stale_threads
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


THREAD_CONTENT_VECTORIZE_TASK = "thread.content.vectorize"


@async_shared_broker.task(task_name=THREAD_CONTENT_VECTORIZE_TASK)
async def run_thread_content_vectorization(thread_id: str) -> JSONObject:
	"""reconcile transcript passage vectors and the thread point."""
	async with async_session_local() as session:
		typeid = TypeID(thread_id)
		summaries = await reconcile_thread_content_vectors(session, thread_ids=[typeid])
		await vectorize_stale_threads([typeid], session)
		await session.commit()
	return summaries[0]


async def schedule_thread_content_vectorization(thread_id: TypeID) -> bool:
	"""enqueue idempotent content vectorization for one thread."""
	if boot_settings.TESTING or not settings.assets.thread_passages.enabled:
		return False
	await run_thread_content_vectorization.kiq(str(thread_id))
	return True
