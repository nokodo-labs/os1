"""E2B code interpreter client.

async wrapper around the e2b-code-interpreter SDK.
does not depend on any application-level code.
"""

from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import dataclass, field
from typing import cast

from e2b_code_interpreter import AsyncSandbox


logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATE = "code-interpreter-v1"
_DEFAULT_TIMEOUT = 60


@dataclass(frozen=True, slots=True)
class ExecutionResult:
	"""result of a code execution in the sandbox."""

	stdout: str = ""
	stderr: str = ""
	results: list[str] = field(default_factory=list)
	error: dict[str, str] | None = None
	files: list[FileEntry] = field(default_factory=list)
	sandbox_id: str = ""


@dataclass(frozen=True, slots=True)
class FileEntry:
	"""a file produced during execution."""

	filename: str
	content: bytes
	mime_type: str


class E2BClient:
	"""async client for E2B code interpreter sandboxes.

	supports creating new sandboxes, reconnecting to existing ones,
	executing code, and managing files within the sandbox.
	"""

	def __init__(
		self,
		*,
		api_key: str,
		template: str = _DEFAULT_TEMPLATE,
	) -> None:
		self._api_key = api_key
		self._template = template
		self._sandbox: AsyncSandbox | None = None

	@property
	def sandbox_id(self) -> str | None:
		"""current sandbox id, if connected."""
		if self._sandbox is None:
			return None
		return self._sandbox.sandbox_id

	async def connect(
		self,
		sandbox_id: str | None = None,
	) -> str:
		"""connect to an existing sandbox or create a new one.

		args:
			sandbox_id: id of a paused sandbox to reconnect to.
				if None or reconnection fails, a new sandbox is created.

		returns:
			the sandbox id of the connected sandbox.
		"""
		if sandbox_id:
			try:
				self._sandbox = cast(
					AsyncSandbox,
					await AsyncSandbox.connect(sandbox_id, api_key=self._api_key),
				)
				logger.debug("reconnected to sandbox %s", sandbox_id)
				return self._sandbox.sandbox_id
			except Exception:
				logger.debug(
					"failed to reconnect to sandbox %s, creating new one",
					sandbox_id,
				)

		self._sandbox = await AsyncSandbox.create(
			template=self._template,
			api_key=self._api_key,
		)
		logger.debug("created new sandbox %s", self._sandbox.sandbox_id)
		return self._sandbox.sandbox_id

	async def run_code(
		self,
		code: str,
		*,
		timeout: int = _DEFAULT_TIMEOUT,
	) -> ExecutionResult:
		"""execute Python code in the sandbox.

		args:
			code: Python source code to execute.
			timeout: max execution time in seconds.

		returns:
			ExecutionResult with stdout, stderr, results, and error.

		raises:
			RuntimeError: if not connected to a sandbox.
		"""
		if self._sandbox is None:
			raise RuntimeError("not connected to a sandbox")

		execution = await self._sandbox.run_code(code, timeout=timeout)

		stdout = ""
		if execution.logs.stdout:
			out = execution.logs.stdout
			stdout = "".join(out) if isinstance(out, list) else str(out)

		stderr = ""
		if execution.logs.stderr:
			err = execution.logs.stderr
			stderr = "".join(err) if isinstance(err, list) else str(err)

		results: list[str] = []
		for r in execution.results:
			if hasattr(r, "text") and r.text:
				results.append(r.text)

		# extract images from results + save to sandbox FS
		image_files = await self._extract_images(execution.results)

		error: dict[str, str] | None = None
		if execution.error:
			error = {
				"name": execution.error.name,
				"value": execution.error.value,
				"traceback": execution.error.traceback,
			}

		return ExecutionResult(
			stdout=stdout,
			stderr=stderr,
			results=results,
			error=error,
			files=image_files,
			sandbox_id=self._sandbox.sandbox_id,
		)

	async def upload_file(
		self,
		filename: str,
		content: bytes,
	) -> None:
		"""upload a file to the sandbox working directory."""
		if self._sandbox is None:
			raise RuntimeError("not connected to a sandbox")
		await self._sandbox.files.write(filename, content)

	async def download_file(
		self,
		filename: str,
	) -> bytes | None:
		"""download a file from the sandbox."""
		if self._sandbox is None:
			raise RuntimeError("not connected to a sandbox")
		try:
			content = await self._sandbox.files.read(filename, format="bytes")
			if isinstance(content, str):
				return content.encode("utf-8")
			return content
		except Exception:
			return None

	async def list_files(self, path: str = ".") -> list[str]:
		"""list files in the sandbox directory."""
		if self._sandbox is None:
			raise RuntimeError("not connected to a sandbox")
		entries = await self._sandbox.files.list(path)
		return [f.name for f in entries]

	async def pause(self) -> None:
		"""pause the sandbox (preserves state for reconnection)."""
		if self._sandbox is not None:
			await self._sandbox.beta_pause(api_key=self._api_key)
			logger.debug("paused sandbox %s", self._sandbox.sandbox_id)

	async def _extract_images(
		self,
		results: object,
	) -> list[FileEntry]:
		"""extract image data from execution results.

		saves images to the sandbox filesystem and returns metadata.
		"""
		images: list[FileEntry] = []
		if not hasattr(results, "__iter__"):
			return images

		for result in results:  # type: ignore[union-attr]
			for ext in ("png", "jpeg", "svg", "pdf"):
				data_b64 = getattr(result, ext, None)
				if not data_b64:
					continue
				try:
					data = base64.b64decode(data_b64)
					filename = f"chart_{uuid.uuid4().hex[:8]}.{ext}"
					if self._sandbox is not None:
						await self._sandbox.files.write(filename, data)
					images.append(
						FileEntry(
							filename=filename,
							content=data,
							mime_type=f"image/{ext}",
						)
					)
				except Exception:
					pass

		return images


__all__ = [
	"E2BClient",
	"ExecutionResult",
	"FileEntry",
]
