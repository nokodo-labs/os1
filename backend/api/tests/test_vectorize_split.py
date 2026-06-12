"""unit coverage for dense_text overflow splitting (split_for_embedding).

pure unit tests - the embedding limit, token counter, and chunker are
monkeypatched so the piece-assembly logic can be exercised without a model,
db, or qdrant connection.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.service import vectorize
from api.v1.service.vectorize import VectorSpec, split_for_embedding
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.adapters.base.chunkers import ContentChunk
from nokodo_ai.utils.tokens import CHARS_PER_TOKEN


@dataclass
class _Doc:
	id: str
	dense: str
	bm25: str


def _spec() -> VectorSpec[_Doc]:
	async def _never(*_: object) -> bool:
		return False

	return VectorSpec(
		resource_type=VectorChunkResourceType.NOTE,
		resource_id=lambda d: d.id,
		dense_text=lambda d: d.dense,
		bm25_text=lambda d: d.bm25,
		metadata=lambda d: {},
		should_revectorize=_never,
	)


def _patch(
	monkeypatch: pytest.MonkeyPatch,
	limit: int,
	counts: list[int] | None,
) -> None:
	async def _limit(session: object = None) -> int:
		return limit

	async def _count(texts: list[str], session: object = None) -> list[int] | None:
		return counts

	monkeypatch.setattr(vectorize, "get_embedding_input_limit", _limit)
	monkeypatch.setattr(vectorize, "count_input_tokens", _count)


def _patch_chunks(
	monkeypatch: pytest.MonkeyPatch,
	chunks: list[ContentChunk],
) -> None:
	async def _chunk(spec: object, dense: str) -> list[ContentChunk]:
		return chunks

	monkeypatch.setattr(vectorize, "_chunk_dense_text", _chunk)


@pytest.mark.asyncio
async def test_blank_text_yields_no_pieces(monkeypatch: pytest.MonkeyPatch) -> None:
	_patch(monkeypatch, limit=100, counts=[0])
	pieces = await split_for_embedding(
		_spec(), _Doc(id="n1", dense="   ", bm25="x"), AsyncSession()
	)
	assert pieces == []


@pytest.mark.asyncio
async def test_under_limit_single_piece_keeps_bm25(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_patch(monkeypatch, limit=100, counts=[10])
	doc = _Doc(id="n1", dense="dense body", bm25="bm25 body")
	pieces = await split_for_embedding(_spec(), doc, AsyncSession())
	assert len(pieces) == 1
	piece = pieces[0]
	assert piece.embed_text == "dense body"
	assert piece.content == "bm25 body"
	assert piece.chunk_index == 0
	assert piece.chunk_count == 1


@pytest.mark.asyncio
async def test_over_limit_splits_into_indexed_pieces(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_patch(monkeypatch, limit=50, counts=[999])
	_patch_chunks(
		monkeypatch,
		[
			ContentChunk(index=0, total=3, text="piece0", metadata={"char_start": 0}),
			ContentChunk(index=1, total=3, text="piece1", metadata={"char_start": 6}),
			ContentChunk(index=2, total=3, text="piece2", metadata={"char_start": 12}),
		],
	)
	doc = _Doc(id="n1", dense="x" * 9000, bm25="x" * 9000)
	pieces = await split_for_embedding(_spec(), doc, AsyncSession())
	assert [p.chunk_index for p in pieces] == [0, 1, 2]
	assert all(p.chunk_count == 3 for p in pieces)
	# each chunk indexes its own slice for both embedding and bm25.
	assert [p.embed_text for p in pieces] == ["piece0", "piece1", "piece2"]
	assert [p.content for p in pieces] == ["piece0", "piece1", "piece2"]
	assert pieces[0].metadata == {"char_start": 0}


@pytest.mark.asyncio
async def test_estimate_fallback_triggers_split(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# no exact tokenizer -> count_input_tokens returns None; estimate is used.
	_patch(monkeypatch, limit=5, counts=None)
	_patch_chunks(
		monkeypatch,
		[
			ContentChunk(index=0, total=2, text="a", metadata={}),
			ContentChunk(index=1, total=2, text="b", metadata={}),
		],
	)
	doc = _Doc(id="n1", dense="x" * 400, bm25="x" * 400)
	pieces = await split_for_embedding(_spec(), doc, AsyncSession())
	assert len(pieces) == 2


@pytest.mark.asyncio
async def test_oversized_chunk_is_truncated_by_guard(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	limit = 10
	_patch(monkeypatch, limit=limit, counts=[999])
	_patch_chunks(
		monkeypatch,
		[ContentChunk(index=0, total=1, text="y" * 1000, metadata={})],
	)
	doc = _Doc(id="n1", dense="y" * 1000, bm25="y" * 1000)
	pieces = await split_for_embedding(_spec(), doc, AsyncSession())
	assert len(pieces) == 1
	assert len(pieces[0].embed_text) <= int(limit * CHARS_PER_TOKEN)


@pytest.mark.asyncio
async def test_empty_chunk_result_falls_back_to_single_piece(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	_patch(monkeypatch, limit=5, counts=[999])
	_patch_chunks(monkeypatch, [])
	doc = _Doc(id="n1", dense="dense body", bm25="bm25 body")
	pieces = await split_for_embedding(_spec(), doc, AsyncSession())
	assert len(pieces) == 1
	assert pieces[0].content == "bm25 body"
