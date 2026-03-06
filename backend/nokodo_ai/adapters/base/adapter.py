"""base adapter lifecycle.

all concrete provider adapters should implement this so callers can reliably
clean up resources via `await adapter.close()`.
"""

from __future__ import annotations

from abc import ABC
from typing import Self


class BaseAdapter(ABC):
	"""base class for all adapters."""

	async def close(self) -> None:
		"""close resources held by this adapter (default: no-op)."""
		return None

	async def __aenter__(self) -> Self:
		return self

	async def __aexit__(
		self,
		exc_type: type[BaseException] | None,
		exc: BaseException | None,
		tb: object | None,
	) -> None:
		await self.close()
