"""nokodo_ai Markdown chunker adapter."""

from __future__ import annotations

from typing import Literal

from nokodo_ai.adapters.base.chunkers import (
	BaseChunkerAdapter,
	ChunkingParams,
	ContentChunk,
)
from nokodo_ai.adapters.base.loaders import Text
from nokodo_ai.utils.tokens import CHARS_PER_TOKEN

from .recursive import _chunks_from_ranges, _normalize_text, _recursive_chunk_ranges


class MarkdownChunkerAdapter(BaseChunkerAdapter):
	"""chunker adapter that preserves Markdown section boundaries."""

	type: Literal["nokodo_ai.markdown"] = "nokodo_ai.markdown"
	name: Literal["markdown"] = "markdown"

	def supports(self, text: Text, params: ChunkingParams) -> bool:
		return text.status == "loaded" and text.format == "markdown"

	async def chunk(
		self,
		text: Text,
		params: ChunkingParams,
	) -> list[ContentChunk]:
		normalized = _normalize_text(text.content)
		if not self.supports(text, params) or not normalized:
			return []
		target_chars = max(1, int(params.target_tokens * CHARS_PER_TOKEN))
		overlap_chars = max(0, int(params.overlap_tokens * CHARS_PER_TOKEN))
		ranges = _markdown_chunk_ranges(
			normalized,
			target_chars,
			overlap_chars,
			params.max_chunks,
		)
		return _chunks_from_ranges(normalized, ranges, text.metadata)


def _markdown_chunk_ranges(
	text: str,
	target_chars: int,
	overlap_chars: int,
	max_chunks: int | None,
) -> list[tuple[int, int]]:
	"""split Markdown text while keeping sections together when possible."""
	unit_ranges = _markdown_unit_ranges(text)
	if not unit_ranges:
		return []
	ranges: list[tuple[int, int]] = []
	current_units: list[tuple[int, int]] = []
	for unit_start, unit_end in unit_ranges:
		if unit_end <= unit_start:
			continue
		if unit_end - unit_start > target_chars:
			if current_units:
				_emit_markdown_range(ranges, current_units, max_chunks)
				current_units = _overlap_units(current_units, overlap_chars)
			remaining_chunks = None if max_chunks is None else max_chunks - len(ranges)
			for start, end in _recursive_chunk_ranges(
				text[unit_start:unit_end],
				target_chars,
				overlap_chars,
				remaining_chunks,
			):
				ranges.append((unit_start + start, unit_start + end))
				if _reached_max_chunks(ranges, max_chunks):
					return ranges
			current_units = []
			continue
		candidate_units = [*current_units, (unit_start, unit_end)]
		if current_units and _range_size(candidate_units) > target_chars:
			_emit_markdown_range(ranges, current_units, max_chunks)
			if _reached_max_chunks(ranges, max_chunks):
				return ranges
			current_units = [
				*_overlap_units(current_units, overlap_chars),
				(unit_start, unit_end),
			]
		else:
			current_units = candidate_units
	if current_units and not _reached_max_chunks(ranges, max_chunks):
		_emit_markdown_range(ranges, current_units, max_chunks)
	if max_chunks is None:
		return ranges
	return ranges[:max_chunks]


def _markdown_unit_ranges(text: str) -> list[tuple[int, int]]:
	"""find heading and blank-line delimited Markdown units."""
	units: list[tuple[int, int]] = []
	lines = text.splitlines(keepends=True)
	block_start = 0
	offset = 0
	in_code_block = False
	for line in lines:
		line_start = offset
		line_end = line_start + len(line)
		stripped = line.strip()
		if stripped.startswith("```") or stripped.startswith("~~~"):
			in_code_block = not in_code_block
		if (
			not in_code_block
			and _is_markdown_heading(stripped)
			and line_start > block_start
		):
			units.append((block_start, line_start))
			block_start = line_start
		if not in_code_block and stripped == "":
			units.append((block_start, line_end))
			block_start = line_end
		offset = line_end
	if block_start < len(text):
		units.append((block_start, len(text)))
	return [(start, end) for start, end in units if text[start:end].strip()]


def _is_markdown_heading(stripped_line: str) -> bool:
	"""return whether a stripped line is a Markdown ATX heading."""
	if not stripped_line.startswith("#"):
		return False
	marker, _, _title = stripped_line.partition(" ")
	return 1 <= len(marker) <= 6 and set(marker) == {"#"}


def _emit_markdown_range(
	ranges: list[tuple[int, int]],
	units: list[tuple[int, int]],
	max_chunks: int | None,
) -> None:
	"""append a range for the current Markdown units if under the cap."""
	if _reached_max_chunks(ranges, max_chunks) or not units:
		return
	ranges.append((units[0][0], units[-1][1]))


def _reached_max_chunks(
	ranges: list[tuple[int, int]],
	max_chunks: int | None,
) -> bool:
	"""return whether the emitted range count reached the configured cap."""
	return max_chunks is not None and len(ranges) >= max_chunks


def _overlap_units(
	units: list[tuple[int, int]],
	overlap_chars: int,
) -> list[tuple[int, int]]:
	"""select trailing Markdown units that fit the requested overlap."""
	if overlap_chars <= 0:
		return []
	selected: list[tuple[int, int]] = []
	total = 0
	for start, end in reversed(units):
		length = end - start
		if selected and total + length > overlap_chars:
			break
		selected.append((start, end))
		total += length
	return list(reversed(selected))


def _range_size(units: list[tuple[int, int]]) -> int:
	"""return the total character span covered by Markdown units."""
	if not units:
		return 0
	return units[-1][1] - units[0][0]
