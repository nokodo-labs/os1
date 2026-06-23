"""nokodo_ai semantic chunker adapter."""

from __future__ import annotations

import logging
import re
from math import sqrt
from typing import Literal

from pydantic import ConfigDict

from nokodo_ai.adapters.base.chunkers import (
	BaseChunkerAdapter,
	ChunkingParams,
	ContentChunk,
)
from nokodo_ai.adapters.base.loaders import Text
from nokodo_ai.adapters.nokodo_ai.recursive import (
	RecursiveChunkerAdapter,
	_chunks_from_ranges,
	_normalize_text,
)
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.tokens import estimate_tokens


logger = logging.getLogger(__name__)


class SemanticChunkerAdapter(BaseChunkerAdapter):
	"""chunker adapter that splits on topic shifts via sentence-embedding distance."""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	type: Literal["nokodo_ai.semantic"] = "nokodo_ai.semantic"
	name: Literal["semantic"] = "semantic"

	embedder: EmbeddingModel
	breakpoint_percentile: float = 95.0
	min_sentences_per_chunk: int = 2
	buffer_size: int = 1

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

		sentences = _split_sentences(normalized)

		# short-circuit: need at least 2 sentences to compare
		if len(sentences) < 2:
			return _chunks_from_ranges(
				normalized, [(0, len(normalized))], text.metadata
			)

		# build windowed strings and embed in one batch
		windows = _build_windows(sentences, self.buffer_size)
		try:
			embeddings = await self.embedder.embed(windows, input_type="document")
			if len(embeddings) != len(sentences):
				raise ValueError(
					f"expected {len(sentences)} embeddings, got {len(embeddings)}"
				)
		except Exception:
			logger.warning(
				"semantic chunker: embedding failed, falling back to recursive"
			)
			return await RecursiveChunkerAdapter().chunk(text, params)

		# compute cosine distances between consecutive window embeddings
		distances = [
			_cosine_distance(embeddings[i], embeddings[i + 1])
			for i in range(len(embeddings) - 1)
		]

		# find breakpoints above the percentile threshold;
		# skip when all gaps are zero (no meaningful signal to split on)
		boundary_set: set[int] = set()
		if max(distances) > 0.0:
			threshold = _percentile(distances, self.breakpoint_percentile)
			boundary_set = {i + 1 for i, d in enumerate(distances) if d >= threshold}

		# group sentences into contiguous segments
		segments: list[list[int]] = []
		current: list[int] = [0]
		for i in range(1, len(sentences)):
			if i in boundary_set:
				segments.append(current)
				current = [i]
			else:
				current.append(i)
		segments.append(current)

		# enforce token budget by sub-splitting at sentence granularity
		segments = _enforce_token_budget(segments, sentences, params.target_tokens)

		# merge segments that are below the minimum sentence count,
		# then re-enforce budget because merging can exceed target_tokens
		segments = _merge_short_segments(
			segments, distances, self.min_sentences_per_chunk
		)
		segments = _enforce_token_budget(segments, sentences, params.target_tokens)

		# clamp to max_chunks by merging across lowest-distance boundaries
		if params.max_chunks is not None:
			segments = _clamp_segments(segments, distances, params.max_chunks)

		# build char ranges, extending back for overlap
		ranges = _segments_to_ranges(sentences, segments, params.overlap_tokens)

		return _chunks_from_ranges(normalized, ranges, text.metadata)


# ---------------------------------------------------------------------------
# sentence splitting
# ---------------------------------------------------------------------------

# naive regex splitter: splits on whitespace after terminal punctuation.
# known limitation: breaks on abbreviations ("dr.", "u.s."), decimal numbers,
# and other non-terminal uses of punctuation. good enough for v1; a proper
# sentencizer (e.g. spacy, pysbd) can be swapped in here later without
# touching the rest of the algorithm.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
	"""split text into (stripped_text, char_start, char_end) triples."""
	sentences: list[tuple[str, int, int]] = []
	prev = 0
	for m in _SENTENCE_SPLIT_RE.finditer(text):
		span = text[prev : m.start()]
		stripped = span.strip()
		if stripped:
			sentences.append((stripped, prev, m.start()))
		prev = m.end()
	remaining = text[prev:].strip()
	if remaining:
		sentences.append((remaining, prev, len(text)))
	return sentences


# ---------------------------------------------------------------------------
# embedding windows
# ---------------------------------------------------------------------------


def _build_windows(
	sentences: list[tuple[str, int, int]],
	buffer_size: int,
) -> list[str]:
	"""build a context window string for each sentence using ±buffer neighbors."""
	windows: list[str] = []
	n = len(sentences)
	for i in range(n):
		start = max(0, i - buffer_size)
		end = min(n, i + buffer_size + 1)
		windows.append(" ".join(s[0] for s in sentences[start:end]))
	return windows


# ---------------------------------------------------------------------------
# vector math
# ---------------------------------------------------------------------------


def _cosine_distance(a: list[float], b: list[float]) -> float:
	"""cosine distance (1 - similarity) between two vectors."""
	dot = sum(x * y for x, y in zip(a, b))
	norm_a = sqrt(sum(x * x for x in a))
	norm_b = sqrt(sum(x * x for x in b))
	if norm_a == 0.0 or norm_b == 0.0:
		return 1.0
	similarity = dot / (norm_a * norm_b)
	return 1.0 - max(-1.0, min(1.0, similarity))


def _percentile(values: list[float], p: float) -> float:
	"""compute the p-th percentile using linear interpolation."""
	if not values:
		return 0.0
	sorted_vals = sorted(values)
	k = (len(sorted_vals) - 1) * p / 100.0
	low = int(k)
	frac = k - low
	if low + 1 >= len(sorted_vals):
		return sorted_vals[low]
	return sorted_vals[low] * (1.0 - frac) + sorted_vals[low + 1] * frac


# ---------------------------------------------------------------------------
# segment operations
# ---------------------------------------------------------------------------


def _enforce_token_budget(
	segments: list[list[int]],
	sentences: list[tuple[str, int, int]],
	target_tokens: int,
) -> list[list[int]]:
	"""sub-split segments that exceed the token budget at sentence granularity."""
	result: list[list[int]] = []
	for seg in segments:
		seg_text = " ".join(sentences[i][0] for i in seg)
		if estimate_tokens(seg_text) <= target_tokens:
			result.append(seg)
			continue
		# greedy sub-split by token budget
		current_sub: list[int] = []
		current_tokens = 0
		for i in seg:
			s_tokens = estimate_tokens(sentences[i][0])
			if current_sub and current_tokens + s_tokens > target_tokens:
				result.append(current_sub)
				current_sub = [i]
				current_tokens = s_tokens
			else:
				current_sub.append(i)
				current_tokens += s_tokens
		if current_sub:
			result.append(current_sub)
	return result


def _merge_short_segments(
	segments: list[list[int]],
	sentence_distances: list[float],
	min_sentences: int,
) -> list[list[int]]:
	"""merge segments shorter than min_sentences into the lowest-distance neighbor."""
	segs = [list(s) for s in segments]
	changed = True
	while changed:
		changed = False
		for i, seg in enumerate(segs):
			if len(seg) >= min_sentences:
				continue
			# find the boundary distance to each neighbor
			left_dist: float | None = None
			right_dist: float | None = None
			if i > 0:
				# boundary at last sentence of left neighbor
				left_dist = sentence_distances[segs[i - 1][-1]]
			if i < len(segs) - 1:
				# boundary at last sentence of current segment
				right_dist = sentence_distances[segs[i][-1]]
			if left_dist is None and right_dist is None:
				break
			if left_dist is None:
				merge_target = i + 1
			elif right_dist is None:
				merge_target = i - 1
			elif left_dist <= right_dist:
				merge_target = i - 1
			else:
				merge_target = i + 1
			if merge_target < i:
				segs[merge_target] = segs[merge_target] + segs[i]
			else:
				segs[merge_target] = segs[i] + segs[merge_target]
			segs.pop(i)
			changed = True
			break
	return segs


def _clamp_segments(
	segments: list[list[int]],
	sentence_distances: list[float],
	max_chunks: int,
) -> list[list[int]]:
	"""merge adjacent segments across the lowest boundary until at most
	max_chunks remain.
	"""
	segs = [list(s) for s in segments]
	while len(segs) > max_chunks:
		# find the boundary with the smallest distance
		min_dist = float("inf")
		min_idx = 0
		for i in range(len(segs) - 1):
			bd = sentence_distances[segs[i][-1]]
			if bd < min_dist:
				min_dist = bd
				min_idx = i
		segs[min_idx] = segs[min_idx] + segs[min_idx + 1]
		segs.pop(min_idx + 1)
	return segs


def _segments_to_ranges(
	sentences: list[tuple[str, int, int]],
	segments: list[list[int]],
	overlap_tokens: int,
) -> list[tuple[int, int]]:
	"""convert sentence-index segments to (char_start, char_end) ranges with overlap."""
	ranges: list[tuple[int, int]] = []
	for seg_idx, seg in enumerate(segments):
		if not seg:
			continue
		char_end = sentences[seg[-1]][2]
		# extend start backwards for overlap from the previous segment
		char_start = sentences[seg[0]][1]
		if overlap_tokens > 0 and seg_idx > 0:
			prev_seg = segments[seg_idx - 1]
			accumulated = 0
			for j in reversed(prev_seg):
				tokens = estimate_tokens(sentences[j][0])
				if accumulated + tokens > overlap_tokens:
					break
				accumulated += tokens
				char_start = sentences[j][1]
		ranges.append((char_start, char_end))
	return ranges
