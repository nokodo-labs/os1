"""unit tests for vectorization fingerprint verification.

pure unit tests - no db, no qdrant connection required. the scroll call is
monkeypatched so filter_unvectorized can be exercised against crafted chunks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.settings import settings
from api.v1.service import vectorize
from api.v1.service.vectorize import (
	CONFIG_FP_KEY,
	PIPELINE_VERSION_KEY,
	VECTORIZATION_PIPELINE_VERSION,
	StaleBy,
	VectorSpec,
	chunk_stamps_stale,
	chunks_match_fingerprint,
	filter_unvectorized,
	resource_fingerprint,
	vectorization_config_fp,
)
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.adapters.base.vectorstores import Chunk


@dataclass
class _Doc:
	id: str
	text: str
	tag: str


def _doc_spec() -> VectorSpec[_Doc]:
	async def _never(*_: object) -> bool:
		return False

	return VectorSpec(
		resource_type=VectorChunkResourceType.MEMORY,
		resource_id=lambda d: d.id,
		dense_text=lambda d: d.text,
		bm25_text=lambda d: d.text,
		metadata=lambda d: {
			"resource_type": VectorChunkResourceType.MEMORY.value,
			"tag": d.tag,
		},
		should_revectorize=_never,
	)


def _chunk(
	resource_id: str,
	fingerprint: str,
	chunk_index: int = 0,
	chunk_count: int = 1,
) -> Chunk:
	return Chunk(
		id=f"{resource_id}-{chunk_index}",
		content="body",
		embedding=[0.0, 0.0],
		metadata={
			"resource_id": resource_id,
			"vec_fingerprint": fingerprint,
			"chunk_index": chunk_index,
			"chunk_count": chunk_count,
		},
	)


# resource_fingerprint


def test_vectorization_config_fp_tracks_chunking_settings(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	base = vectorization_config_fp()
	assert base == vectorization_config_fp()
	monkeypatch.setattr(settings.assets.content_vectorization, "target_tokens", 999)
	assert vectorization_config_fp() != base


def test_chunk_stamps_stale_gated_by_triggers(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""provenance staleness only counts when the pipeline's triggers enable it."""
	old = Chunk(
		id="c1",
		content="body",
		embedding=[0.0],
		metadata={
			"resource_id": "m1",
			PIPELINE_VERSION_KEY: VECTORIZATION_PIPELINE_VERSION - 1,
			CONFIG_FP_KEY: "other-config",
		},
	)
	assert chunk_stamps_stale([old]) is False
	monkeypatch.setattr(
		settings.assets.revectorize.resources, "on_pipeline_version", True
	)
	assert chunk_stamps_stale([old]) is True


def test_chunk_stamps_stale_detects_config_mismatch() -> None:
	"""a config-stale chunk matches by={CONFIG} and NOT by={PIPELINE_VERSION}."""
	config_stale = Chunk(
		id="c1",
		content="body",
		embedding=[0.0],
		metadata={
			"resource_id": "m1",
			PIPELINE_VERSION_KEY: VECTORIZATION_PIPELINE_VERSION,
			CONFIG_FP_KEY: "other-config",
		},
	)
	assert chunk_stamps_stale([config_stale], by={StaleBy.CONFIG}) is True
	assert chunk_stamps_stale([config_stale], by={StaleBy.PIPELINE_VERSION}) is False


def test_chunk_stamps_stale_config_trigger_knob(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the on_config_change knob gates config staleness in trigger mode."""
	config_stale = Chunk(
		id="c1",
		content="body",
		embedding=[0.0],
		metadata={
			"resource_id": "m1",
			PIPELINE_VERSION_KEY: VECTORIZATION_PIPELINE_VERSION,
			CONFIG_FP_KEY: "other-config",
		},
	)
	assert chunk_stamps_stale([config_stale]) is False
	monkeypatch.setattr(settings.assets.revectorize.resources, "on_config_change", True)
	assert chunk_stamps_stale([config_stale]) is True


def test_build_chunk_stamps_provenance() -> None:
	"""built chunks carry the current pipeline version and config fingerprint."""
	spec = _doc_spec()
	doc = _Doc(id="m1", text="hello", tag="a")
	chunk = vectorize.build_chunk(spec, doc, embedding=[0.0, 0.0])
	assert chunk.metadata[PIPELINE_VERSION_KEY] == VECTORIZATION_PIPELINE_VERSION
	assert chunk.metadata[CONFIG_FP_KEY] == vectorization_config_fp()
	# a freshly built chunk is provenance-current for every cause.
	assert (
		chunk_stamps_stale([chunk], by={StaleBy.PIPELINE_VERSION, StaleBy.CONFIG})
		is False
	)


def test_chunk_stamps_stale_explicit_cause_bypasses_triggers() -> None:
	"""explicit by= targets one cause regardless of the trigger knobs."""
	current_config = vectorization_config_fp()
	old_version = Chunk(
		id="c1",
		content="body",
		embedding=[0.0],
		metadata={
			"resource_id": "m1",
			PIPELINE_VERSION_KEY: VECTORIZATION_PIPELINE_VERSION - 1,
			CONFIG_FP_KEY: current_config,
		},
	)
	assert chunk_stamps_stale([old_version], by={StaleBy.PIPELINE_VERSION}) is True
	assert chunk_stamps_stale([old_version], by={StaleBy.CONFIG}) is False
	assert (
		chunk_stamps_stale([old_version], by={StaleBy.PIPELINE_VERSION, StaleBy.CONFIG})
		is True
	)
	current = Chunk(
		id="c2",
		content="body",
		embedding=[0.0],
		metadata={
			"resource_id": "m1",
			PIPELINE_VERSION_KEY: VECTORIZATION_PIPELINE_VERSION,
			CONFIG_FP_KEY: current_config,
		},
	)
	assert chunk_stamps_stale([current], by={StaleBy.PIPELINE_VERSION}) is False
	assert chunk_stamps_stale([current], by={StaleBy.CONFIG}) is False


def test_resource_fingerprint_is_stable() -> None:
	spec = _doc_spec()
	doc = _Doc(id="m1", text="hello", tag="a")
	assert resource_fingerprint(spec, doc) == resource_fingerprint(spec, doc)


def test_resource_fingerprint_changes_with_content() -> None:
	spec = _doc_spec()
	base = resource_fingerprint(spec, _Doc(id="m1", text="hello", tag="a"))
	assert base != resource_fingerprint(spec, _Doc(id="m1", text="world", tag="a"))
	assert base != resource_fingerprint(spec, _Doc(id="m1", text="hello", tag="b"))


def test_resource_fingerprint_ignores_acl_fields() -> None:
	async def _never(*_: object) -> bool:
		return False

	spec: VectorSpec[_Doc] = VectorSpec(
		resource_type=VectorChunkResourceType.NOTE,
		resource_id=lambda d: d.id,
		dense_text=lambda d: d.text,
		bm25_text=lambda d: d.text,
		metadata=lambda d: {
			"tag": d.tag,
			"allowed_user_ids": [d.id],
			"allowed_group_ids": [],
			"allowed_role_ids": [],
		},
		should_revectorize=_never,
	)
	doc = _Doc(id="n1", text="hi", tag="a")
	with_acl = resource_fingerprint(spec, doc)
	doc_other_acl = _Doc(id="n2", text="hi", tag="a")
	# the acl-derived field differs (uses id) but must not affect the digest
	assert with_acl == resource_fingerprint(spec, doc_other_acl)


# chunks_match_fingerprint


def test_chunks_match_empty_is_false() -> None:
	assert chunks_match_fingerprint([], "fp") is False


def test_chunks_match_single_chunk() -> None:
	assert chunks_match_fingerprint([_chunk("m1", "fp")], "fp") is True


def test_chunks_match_wrong_fingerprint() -> None:
	assert chunks_match_fingerprint([_chunk("m1", "old")], "new") is False


def test_chunks_match_multi_chunk_complete() -> None:
	chunks = [
		_chunk("f1", "fp", chunk_index=0, chunk_count=3),
		_chunk("f1", "fp", chunk_index=1, chunk_count=3),
		_chunk("f1", "fp", chunk_index=2, chunk_count=3),
	]
	assert chunks_match_fingerprint(chunks, "fp") is True


def test_chunks_match_multi_chunk_missing_index() -> None:
	chunks = [
		_chunk("f1", "fp", chunk_index=0, chunk_count=3),
		_chunk("f1", "fp", chunk_index=2, chunk_count=3),
	]
	assert chunks_match_fingerprint(chunks, "fp") is False


def test_chunks_match_inconsistent_count() -> None:
	chunks = [
		_chunk("f1", "fp", chunk_index=0, chunk_count=2),
		_chunk("f1", "fp", chunk_index=1, chunk_count=3),
	]
	assert chunks_match_fingerprint(chunks, "fp") is False


def test_chunks_match_missing_bookkeeping_is_false() -> None:
	bad = Chunk(
		id="x",
		content="body",
		embedding=[0.0],
		metadata={"resource_id": "m1", "vec_fingerprint": "fp"},
	)
	assert chunks_match_fingerprint([bad], "fp") is False


# filter_unvectorized


@pytest.mark.asyncio
async def test_filter_unvectorized_drops_current_keeps_stale(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	spec = _doc_spec()
	current = _Doc(id="m1", text="hello", tag="a")
	stale = _Doc(id="m2", text="hello", tag="a")
	missing = _Doc(id="m3", text="hello", tag="a")

	stored = [
		_chunk("m1", resource_fingerprint(spec, current)),
		_chunk("m2", "stale-fingerprint"),
	]

	async def _fake_scroll(
		resource_type: VectorChunkResourceType,
		resource_ids: Sequence[str],
		session: object,
	) -> list[Chunk]:
		return [c for c in stored if c.metadata["resource_id"] in set(resource_ids)]

	monkeypatch.setattr(
		vectorize,
		"scroll_resource_chunks",
		_fake_scroll,
	)

	pending = await filter_unvectorized(
		spec, [current, stale, missing], session=AsyncSession()
	)
	pending_ids = {doc.id for doc in pending}
	assert pending_ids == {"m2", "m3"}


@pytest.mark.asyncio
async def test_filter_unvectorized_empty_returns_empty() -> None:
	spec = _doc_spec()
	assert await filter_unvectorized(spec, [], session=AsyncSession()) == []
