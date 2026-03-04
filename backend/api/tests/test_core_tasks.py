"""tests for api.core.tasks - shared background task utilities."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from api.core.tasks import _background_tasks, _on_task_done, create_background_task


class TestCreateBackgroundTask:
	"""tests for create_background_task."""

	@pytest.mark.asyncio()
	async def test_task_completes_and_is_removed(self) -> None:
		"""a successful task is removed from _background_tasks after completion."""
		completed = False

		async def _work() -> str:
			nonlocal completed
			completed = True
			return "done"

		task = create_background_task(_work(), name="test_success")
		assert task in _background_tasks

		result = await task
		assert result == "done"
		assert completed

		# give the done callback a chance to fire
		await asyncio.sleep(0)
		assert task not in _background_tasks

	@pytest.mark.asyncio()
	async def test_task_exception_is_logged(self) -> None:
		"""a failed task logs the exception and is removed from the set."""

		async def _fail() -> None:
			raise RuntimeError("test error")

		task = create_background_task(_fail(), name="test_fail")
		assert task in _background_tasks

		with patch("api.core.tasks.logger") as mock_logger:
			# wait for the task to finish (it will raise)
			with pytest.raises(RuntimeError, match="test error"):
				await task

			# give the done callback a chance to fire
			await asyncio.sleep(0)

			mock_logger.exception.assert_called_once()
			assert "test_fail" in mock_logger.exception.call_args[0][1]

		assert task not in _background_tasks

	@pytest.mark.asyncio()
	async def test_task_has_name(self) -> None:
		"""the task is created with the given name."""

		async def _noop() -> None:
			pass

		task = create_background_task(_noop(), name="my_task")
		assert task.get_name() == "my_task"
		await task
		await asyncio.sleep(0)

	@pytest.mark.asyncio()
	async def test_cancelled_task_no_error(self) -> None:
		"""a cancelled task does not log an exception."""

		async def _block() -> None:
			await asyncio.sleep(100)

		task = create_background_task(_block(), name="test_cancel")
		task.cancel()

		with patch("api.core.tasks.logger") as mock_logger:
			with pytest.raises(asyncio.CancelledError):
				await task
			await asyncio.sleep(0)
			mock_logger.exception.assert_not_called()


class TestOnTaskDone:
	"""tests for the _on_task_done callback."""

	def test_cancelled_task(self) -> None:
		task = MagicMock()
		task.cancelled.return_value = True
		_on_task_done(task, "test")
		# no exception access
		task.exception.assert_not_called()

	def test_successful_task(self) -> None:
		task = MagicMock()
		task.cancelled.return_value = False
		task.exception.return_value = None
		_on_task_done(task, "test")

	def test_failed_task_logs(self) -> None:
		task = MagicMock()
		task.cancelled.return_value = False
		exc = RuntimeError("boom")
		task.exception.return_value = exc

		with patch("api.core.tasks.logger") as mock_logger:
			_on_task_done(task, "my_bg_task")
			mock_logger.exception.assert_called_once()
			assert "my_bg_task" in mock_logger.exception.call_args[0][1]
