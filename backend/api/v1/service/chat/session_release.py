"""release the request session around SDK callbacks.

the SDK runs an agent; it does not know what a database session is, so it does
not free ours between steps. we do it here, at our own boundary: every callback
the SDK invokes on our behalf returns its connection to the pool when it ends.

a callback can run minutes apart from the next one (a slow provider, a long
tool), and holding a pooled connection across that is what exhausts the pool.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext


logger = logging.getLogger(__name__)


@asynccontextmanager
async def releasing_session(app_context: AppContext | None) -> AsyncIterator[None]:
	"""return the app context's connection to the pool when the block ends.

	the close is best-effort: a connection that cannot be returned must never
	replace the exception the block was already raising, because that is the
	one describing what actually went wrong.
	"""
	try:
		yield
	finally:
		if app_context is not None:
			try:
				await app_context.session.close()
			except Exception:
				logger.warning("failed to release the session", exc_info=True)
