"""large real-world scenario for media projection + context compaction.

this drives the *actual* projection and compaction primitives together across
hundreds of simulated chat ticks, with summarization mocked, to prove the
protection invariants hold while the conversation grows past a million tokens:

- a HARD-protected media message (the file being read this agent run) is never
  dropped by summarization or pruning, and the model always keeps its bytes.
- SOFT media stays native inside its window, is released to a text reference
  once it ages out, and is recoverable by re-fetching the file (file_get).
- the live (post-compaction) window stays bounded under the budget even as the
  raw conversation volume climbs into the millions of tokens.
- when a hard-protected media message alone cannot fit, the compaction state
  reaches the documented terminal condition instead of cutting the bytes.

the summary model is mocked: the "blocking summarization" step folds the batch
chosen by ``next_summarization_batch`` into a single short system message,
exactly as the real pipeline would, minus the network call.
"""

from __future__ import annotations

from api.settings.settings import AIAttachmentSettings
from api.v1.service.chat.context_compaction.budgets import sum_message_tokens
from api.v1.service.chat.context_compaction.media import (
	project_attachments,
)
from api.v1.service.chat.context_compaction.protection import (
	find_media_protected_index,
	protected_indices,
)
from api.v1.service.chat.context_compaction.pruning import prune_oldest_until
from api.v1.service.chat.context_compaction.summarization import (
	next_summarization_batch,
)
from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	Message,
	SystemMessage,
	TextContent,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.utils.typeid import TypeID


_SUPPORTED = {"images", "audio", "video"}
_BUDGET = 6_000


# -- native media builders (shaped like file_get output) --


def _image(file_id: str, version: str) -> ImageContent:
	return ImageContent(
		filename=f"{file_id}.png",
		media_type="image/png",
		metadata={"file_id": file_id, "fetched": True, "updated_at": version},
	)


def _audio(file_id: str, version: str) -> FileContent:
	return FileContent(
		filename=f"{file_id}.mp3",
		media_type="audio/mpeg",
		metadata={"file_id": file_id, "fetched": True, "updated_at": version},
	)


def _video(file_id: str, version: str) -> FileContent:
	return FileContent(
		filename=f"{file_id}.mp4",
		media_type="video/mp4",
		metadata={"file_id": file_id, "fetched": True, "updated_at": version},
	)


def _pdf(file_id: str, version: str) -> FileContent:
	return FileContent(
		filename=f"{file_id}.pdf",
		media_type="application/pdf",
		metadata={"file_id": file_id, "fetched": True, "updated_at": version},
	)


_MEDIA_BUILDERS = (_image, _audio, _video, _pdf)


class _ChatSim:
	"""a growing chat thread plus the per-tick compaction the pipeline runs."""

	def __init__(self) -> None:
		# the live window the model would actually see, and the parallel id list.
		self.messages: list[Message] = [
			SystemMessage.from_text("you are a helpful assistant.")
		]
		self.ids: list[str | None] = [None]
		self.run_id: TypeID = TypeID("run_0")
		self._seq = 0
		# total tokens the conversation has *ever* produced (never compacted).
		self.produced_tokens = 0
		# bookkeeping for assertions.
		self.released_seen: set[str] = set()

	def _next_id(self) -> str:
		self._seq += 1
		return f"m{self._seq}"

	def _append(self, message: Message, *, persisted: bool = True) -> None:
		mid = self._next_id() if persisted else None
		if mid is not None:
			meta = dict(message.metadata or {})
			meta["_message_id"] = mid
			message = message.model_copy(update={"metadata": meta})
			self.messages.append(message)
			self.ids.append(mid)
		else:
			self.messages.append(message)
			self.ids.append(None)
		self.produced_tokens += sum_message_tokens([message])

	def user(self, text: str, *, starts_run: bool) -> None:
		if starts_run:
			self.run_id = TypeID(f"run_{self._seq + 1}")
		meta: dict[str, object] = {}
		if starts_run:
			meta["run_id"] = str(self.run_id)
		self._append(
			UserMessage(content=[TextContent(text=text)]).model_copy(
				update={"metadata": meta or None}
			)
		)

	def assistant(self, text: str, *, tool_call_id: str | None = None) -> None:
		tool_calls = (
			[ToolCall(id=tool_call_id, name="file_get", arguments="{}")]
			if tool_call_id
			else []
		)
		self._append(
			AssistantMessage(content=[TextContent(text=text)], tool_calls=tool_calls)
		)

	def fetch(
		self, *attachments: object, call_id: str, output: str = "retrieved file(s)"
	) -> None:
		# a file_get tool message carrying native bytes for this agent run.
		self._append(
			ToolMessage(
				tool_call_id=call_id,
				tool_output=output,
				attachments=list(attachments),  # type: ignore[arg-type]
			)
		)

	def plain_tool(self, output: str, *, call_id: str) -> None:
		self._append(ToolMessage(tool_call_id=call_id, tool_output=output))

	# -- compaction, mirroring the pipeline order with a mocked summarizer --

	def _fold_summary(self, start_id: TypeID, end_id: TypeID) -> bool:
		"""replace a chosen batch with one short system summary (mock model)."""
		try:
			start_idx = self.ids.index(str(start_id))
			end_idx = self.ids.index(str(end_id))
		except ValueError:
			return False
		if end_idx < start_idx:
			return False
		summary = SystemMessage.from_text("[summary of earlier conversation]")
		self.messages[start_idx : end_idx + 1] = [summary]
		self.ids[start_idx : end_idx + 1] = [None]
		return True

	def compact(self) -> None:
		# 1. project media before any budget work (this marks hard media and
		# releases aged-out media to references).
		projection = project_attachments(
			self.messages, _SUPPORTED, AIAttachmentSettings()
		)
		self.messages = list(projection.messages)
		self.released_seen.update(str(fid) for fid in projection.newly_released)

		# 2. fit-first cascade: summarize the oldest compressible island, then
		# prune, never crossing a protected index. loop until we fit or stall.
		while sum_message_tokens(self.messages) > _BUDGET and len(self.messages) > 1:
			batch, start_id, end_id = next_summarization_batch(
				self.messages, self.ids, [], token_limit=2_000, run_id=self.run_id
			)
			if batch and start_id and end_id and self._fold_summary(start_id, end_id):
				continue
			before = len(self.messages)
			self.messages, self.ids, _, _ = prune_oldest_until(
				self.messages, self.ids, _BUDGET, self.run_id
			)
			if len(self.messages) == before:
				# nothing left to compress; protected content alone exceeds the
				# budget. the pipeline raises a terminal error here.
				break

	# -- invariant assertions --

	def assert_protection_invariants(self) -> None:
		protected = protected_indices(self.messages, self.run_id)
		# every protected index must still point at a real message in the window.
		assert all(0 <= idx < len(self.messages) for idx in protected)
		# the run-start anchor for the active run is always retained.
		run_anchor = [
			idx
			for idx, msg in enumerate(self.messages)
			if msg.role == "user"
			and str((msg.metadata or {}).get("run_id")) == str(self.run_id)
		]
		assert run_anchor, "active run-start anchor was dropped by compaction"


def _native_file_ids(messages: list[Message]) -> set[str]:
	"""file_ids whose native bytes are still present on a tool message."""
	ids: set[str] = set()
	for msg in messages:
		if not isinstance(msg, ToolMessage):
			continue
		for att in msg.attachments:
			if isinstance(att, (ImageContent, FileContent)):
				fid = (att.metadata or {}).get("file_id")
				if fid:
					ids.add(str(fid))
	return ids


def test_long_running_chat_preserves_protection_under_compaction() -> None:
	sim = _ChatSim()
	body = "word " * 800  # a chunky, realistic message body
	ticks = 400
	hard_survived_every_read = True

	for tick in range(ticks):
		# a new user request starts a new agent run.
		sim.user(f"request {tick}: {body}", starts_run=True)

		# roughly every third run the agent fetches a fresh file (rotating type).
		if tick % 3 == 0:
			fid = f"file_{tick}"
			builder = _MEDIA_BUILDERS[(tick // 3) % len(_MEDIA_BUILDERS)]
			version = f"2026-01-{(tick % 27) + 1:02d}T00:00:00+00:00"
			call_id = f"call_{tick}"
			sim.assistant("let me pull that file.", tool_call_id=call_id)
			sim.fetch(builder(fid, version), call_id=call_id)

			# READ ITERATION: the model is about to consume the fresh bytes. the
			# file is hard-protected here (distance 0), so compaction must keep
			# it native and marked no matter how much history piled up.
			sim.compact()
			sim.assert_protection_invariants()
			native = _native_file_ids(sim.messages)
			marked = find_media_protected_index(sim.messages)
			if fid not in native or marked is None:
				hard_survived_every_read = False
			assert sum_message_tokens(sim.messages) <= _BUDGET + 4_000

		# the agent reasons over a couple more iterations within the run, then
		# answers. by the end of the run the file has decayed to soft (and will
		# be released once the next run starts a new agent turn).
		sim.assistant(f"analysis part one {body}")
		sim.plain_tool("search results", call_id=f"search_{tick}")
		sim.assistant(f"final answer for {tick}: {body}")

		sim.compact()
		sim.assert_protection_invariants()

		# the live window must stay bounded no matter how much history piled up.
		assert sum_message_tokens(sim.messages) <= _BUDGET + 4_000

	assert hard_survived_every_read, "a hard-protected file was dropped"
	# we genuinely streamed well over a million tokens of conversation.
	assert sim.produced_tokens > 1_000_000
	# and aged-out media really did get released to references along the way.
	assert sim.released_seen, "no media was ever released despite long history"


def test_released_media_is_recoverable_by_refetch() -> None:
	sim = _ChatSim()
	body = "word " * 700

	# fetch a file early, then let many runs pass so it ages out of the window.
	sim.user("show me the chart", starts_run=True)
	sim.assistant("fetching", tool_call_id="c0")
	sim.fetch(_image("file_chart", "2026-01-01T00:00:00+00:00"), call_id="c0")
	sim.assistant(f"here it is {body}")
	sim.compact()
	assert "file_chart" in _native_file_ids(sim.messages)

	for tick in range(8):
		sim.user(f"follow up {tick}: {body}", starts_run=True)
		sim.assistant(f"reply {tick}: {body}")
		sim.compact()

	# the chart aged out: no longer native, model only has the text reference.
	assert "file_chart" not in _native_file_ids(sim.messages)
	assert "file_chart" in sim.released_seen

	# the agent re-fetches it on demand -> native bytes are restored. at this
	# read iteration the re-fetched file is hard-protected again.
	sim.user("pull the chart again", starts_run=True)
	sim.assistant("re-fetching", tool_call_id="c_refetch")
	sim.fetch(_image("file_chart", "2026-01-01T00:00:00+00:00"), call_id="c_refetch")
	sim.compact()
	assert "file_chart" in _native_file_ids(sim.messages)
	assert find_media_protected_index(sim.messages) is not None


def test_hard_media_that_busts_budget_reaches_terminal_condition() -> None:
	# a single agent run reads many large files at once; their native bytes alone
	# blow the budget. compaction must NOT drop them - instead it reaches the
	# state the pipeline reports as a clear terminal error (hard media present
	# and still over budget after everything compressible is gone).
	sim = _ChatSim()
	huge = "word " * 4_000

	sim.user("summarize all of these", starts_run=True)
	sim.assistant("reading the batch", tool_call_id="c_batch")
	# eight large files on one read turn (the file_get batch ceiling).
	attachments = [_pdf(f"big_{i}", "2026-01-01T00:00:00+00:00") for i in range(8)]
	# the read iteration: the bytes plus a huge derived output land on the single
	# hard-protected tool message, so that one message alone exceeds the budget.
	sim.fetch(*attachments, call_id="c_batch", output=huge)

	projection = project_attachments(sim.messages, _SUPPORTED, AIAttachmentSettings())
	sim.messages = list(projection.messages)

	# compress everything that is legally compressible.
	sim.messages, sim.ids, _, _ = prune_oldest_until(
		sim.messages, sim.ids, _BUDGET, sim.run_id
	)

	# the hard-protected media tool message is still here, and we are still over
	# budget: this is exactly the branch where the pipeline raises the explicit
	# "fetch fewer files / use a larger context window" terminal error.
	assert find_media_protected_index(sim.messages) is not None
	assert sum_message_tokens(sim.messages) > _BUDGET
