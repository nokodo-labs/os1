"""minimal type stubs for e2b-code-interpreter."""

from enum import Enum
from typing import Any
from datetime import datetime

class FileType(Enum):
	FILE = "file"
	DIR = "dir"

class AsyncSandbox:
	sandbox_id: str
	files: _FileManager
	logs: Any

	@classmethod
	async def create(
		cls, *, template: str = ..., api_key: str = ...
	) -> AsyncSandbox: ...
	@classmethod
	async def connect(cls, sandbox_id: str, *, api_key: str = ...) -> AsyncSandbox: ...
	async def run_code(self, code: str, *, timeout: int = ...) -> _ExecutionResult: ...
	async def beta_pause(self, *, api_key: str = ...) -> None: ...

class _FileManager:
	async def write(self, path: str, data: str | bytes) -> None: ...
	async def read(self, path: str, *, format: str = ...) -> str | bytes: ...
	async def list(self, path: str = ...) -> list[_FileEntry]: ...

class _FileEntry:
	name: str
	type: FileType | None
	path: str
	size: int

class _ExecutionResult:
	logs: _ExecutionLogs
	results: list[_ResultItem]
	error: _ExecutionError | None

class _ExecutionLogs:
	stdout: list[str] | str
	stderr: list[str] | str

class _ResultItem:
	text: str | None
	png: str | None
	jpeg: str | None
	svg: str | None
	pdf: str | None

class _ExecutionError:
	name: str
	value: str
	traceback: str
