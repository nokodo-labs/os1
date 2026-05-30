"""nokodo_ai recursive chunker adapter."""

from __future__ import annotations

from typing import Literal

from nokodo_ai.adapters.base.chunkers import (
	BaseChunkerAdapter,
	ChunkingParams,
	ContentChunk,
)
from nokodo_ai.adapters.base.loaders import Text
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.tokens import CHARS_PER_TOKEN, estimate_tokens


class RecursiveChunkerAdapter(BaseChunkerAdapter):
	"""chunker adapter that splits text by the best nearby boundary."""

	type: Literal["nokodo_ai.recursive"] = "nokodo_ai.recursive"
	name: Literal["recursive"] = "recursive"

	def supports(self, text: Text, params: ChunkingParams) -> bool:
		return text.status == "loaded" and bool(_normalize_text(text.content))

	async def chunk(
		self,
		text: Text,
		params: ChunkingParams,
	) -> list[ContentChunk]:
		normalized = _normalize_text(text.content)
		if not self.supports(text, params):
			return []
		target_chars = max(1, int(params.target_tokens * CHARS_PER_TOKEN))
		overlap_chars = max(0, int(params.overlap_tokens * CHARS_PER_TOKEN))
		ranges = _recursive_chunk_ranges(
			normalized,
			target_chars,
			overlap_chars,
			params.max_chunks,
		)
		return _chunks_from_ranges(normalized, ranges, text.metadata)


def _normalize_text(text: str) -> str:
	"""normalize newlines and trim surrounding whitespace before chunking."""
	return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _recursive_chunk_ranges(
	text: str,
	target_chars: int,
	overlap_chars: int,
	max_chunks: int | None,
) -> list[tuple[int, int]]:
	"""split text into bounded ranges near natural boundaries."""
	ranges: list[tuple[int, int]] = []
	start = 0
	text_length = len(text)
	while start < text_length and (max_chunks is None or len(ranges) < max_chunks):
		end = min(text_length, start + target_chars)
		if end < text_length:
			end = _best_boundary(text, start, end)
		if end <= start:
			end = min(text_length, start + target_chars)
		ranges.append((start, end))
		if end >= text_length:
			break
		start = max(end - overlap_chars, start + 1)
	return ranges

def _chunks_from_ranges(
	text: str,
	ranges: list[tuple[int, int]],
	base_metadata: JSONObject,
) -> list[ContentChunk]:
	"""convert character ranges into content chunks with position metadata."""
	chunks: list[ContentChunk] = []
	line_starts = _line_start_offsets(text)
	for chunk_index, (start, end) in enumerate(ranges):
		chunk_text = text[start:end].strip()
		if not chunk_text:
			continue
		line_start = _line_number_for_offset(line_starts, start)
		line_end = _line_number_for_offset(line_starts, max(start, end - 1))
		metadata: JSONObject = {
			**base_metadata,
			"char_start": start,
			"char_end": end,
			"line_start": line_start,
			"line_end": line_end,
			"token_estimate": estimate_tokens(chunk_text),
		}
		chunks.append(
			ContentChunk(
				index=chunk_index,
				total=0,
				text=chunk_text,
				metadata=metadata,
			)
		)
	total = len(chunks)
	return [
		ContentChunk(
			index=chunk.index,
			total=total,
			text=chunk.text,
			metadata=chunk.metadata,
		)
		for chunk in chunks
	]


def _best_boundary(text: str, start: int, target_end: int) -> int:
	"""find the best split boundary near the target end offset."""
	minimum = start + max(1, int((target_end - start) * 0.5))
	for separator in ("\n\n", "\n", ". ", "; ", ", ", " "):
		position = text.rfind(separator, minimum, target_end)
		if position != -1:
			return position + len(separator)
	return target_end


def _line_start_offsets(text: str) -> list[int]:
	"""return character offsets where each line starts."""
	offsets = [0]
	for index, char in enumerate(text):
		if char == "\n":
			offsets.append(index + 1)
	return offsets


def _line_number_for_offset(line_starts: list[int], offset: int) -> int:
	"""convert a character offset to a one-based line number."""
	line_number = 1
	for index, line_start in enumerate(line_starts, start=1):
		if line_start > offset:
			break
		line_number = index
	return line_number
