"""unit tests for the transcript passage engine."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import count

from api.models.message import MessageType
from api.v1.service.threads.passages import (
	TranscriptPassage,
	build_transcript_passages,
)


_counter = count()
_BASE = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(slots=True)
class _Msg:
	id: str
	parent_id: str | None
	type: MessageType
	text_content: str
	created_at: datetime = field(default_factory=lambda: _BASE)


def _msg(
	mid: str,
	parent: str | None,
	mtype: MessageType,
	text: str,
) -> _Msg:
	return _Msg(
		id=mid,
		parent_id=parent,
		type=mtype,
		text_content=text,
		created_at=_BASE + timedelta(seconds=next(_counter)),
	)


def _build(messages: list[_Msg], target: int = 100, overlap: int = 20):
	return build_transcript_passages(
		messages, target_tokens=target, overlap_tokens=overlap
	)


def test_passages_are_deterministic() -> None:
	messages = [
		_msg("m1", None, MessageType.USER, "how do i configure pgbouncer"),
		_msg("m2", "m1", MessageType.ASSISTANT, "set max_client_conn and pool_mode"),
	]
	first = _build(messages)
	second = _build(messages)
	assert first == second
	assert len(first) == 1
	assert first[0].anchor_message_id == "m1"
	assert first[0].first_message_id == "m1"
	assert first[0].last_message_id == "m2"
	assert first[0].part_index == 0
	assert "user: how do i configure pgbouncer" in first[0].text
	assert "assistant: set max_client_conn" in first[0].text


def test_append_keeps_earlier_passage_geometry_stable() -> None:
	base = [
		_msg("m1", None, MessageType.USER, "alpha " * 15),
		_msg("m2", "m1", MessageType.ASSISTANT, "beta " * 15),
	]
	before = _build(base, target=60, overlap=0)
	extended = [*base, _msg("m3", "m2", MessageType.USER, "gamma " * 15)]
	after = _build(extended, target=60, overlap=0)
	before_keys = {
		(p.first_message_id, p.last_message_id, p.part_index, p.content_hash)
		for p in before
	}
	after_keys = {
		(p.first_message_id, p.last_message_id, p.part_index, p.content_hash)
		for p in after
	}
	assert before_keys <= after_keys
	assert len(after_keys) > len(before_keys)


def test_tool_and_system_messages_are_excluded_but_chain_survives() -> None:
	messages = [
		_msg("m1", None, MessageType.USER, "find the report"),
		_msg("m2", "m1", MessageType.ASSISTANT, "searching now"),
		_msg("m3", "m2", MessageType.TOOL, "raw tool output blob"),
		_msg("m4", "m3", MessageType.ASSISTANT, "found it in q3 folder"),
	]
	passages = _build(messages)
	assert len(passages) == 1
	assert "raw tool output blob" not in passages[0].text
	assert "found it in q3 folder" in passages[0].text


def test_passages_never_cross_branch_points() -> None:
	messages = [
		_msg("m1", None, MessageType.USER, "start topic"),
		_msg("m2a", "m1", MessageType.ASSISTANT, "first answer attempt"),
		_msg("m2b", "m1", MessageType.ASSISTANT, "regenerated answer attempt"),
		_msg("m3", "m2b", MessageType.USER, "follow up on second answer"),
	]
	passages = _build(messages)
	assert all(
		not (
			"first answer attempt" in passage.text
			and "regenerated answer attempt" in passage.text
		)
		for passage in passages
	)
	assert all(
		not (
			"first answer attempt" in passage.text
			and "follow up on second answer" in passage.text
		)
		for passage in passages
	)
	combined = "\n".join(passage.text for passage in passages)
	for text in (
		"start topic",
		"first answer attempt",
		"regenerated answer attempt",
		"follow up on second answer",
	):
		assert text in combined


def test_oversize_message_splits_with_shared_anchor() -> None:
	huge = "code line here\n" * 400
	messages = [_msg("m1", None, MessageType.USER, huge)]
	passages = _build(messages, target=50, overlap=5)
	assert len(passages) > 1
	assert all(p.anchor_message_id == "m1" for p in passages)
	assert [p.part_index for p in passages] == list(range(len(passages)))
	assert all(len(p.content_hash) == 64 for p in passages)


def test_user_turn_starts_new_passage_when_filled() -> None:
	# m1+m2 fill past 60% of target; the next user turn must open a new
	# passage even though it would still fit.
	messages = [
		_msg("m1", None, MessageType.USER, "one " * 40),
		_msg("m2", "m1", MessageType.ASSISTANT, "two " * 40),
		_msg("m3", "m2", MessageType.USER, "three " * 5),
	]
	passages = _build(messages, target=120, overlap=0)
	assert len(passages) == 2
	assert "one " in passages[0].text
	assert "two " in passages[0].text
	assert passages[1].anchor_message_id == "m3"


def test_overlap_carries_context_but_not_anchor() -> None:
	messages = [
		_msg("m1", None, MessageType.USER, "alpha " * 30),
		_msg("m2", "m1", MessageType.ASSISTANT, "beta " * 5),
		_msg("m3", "m2", MessageType.USER, "gamma " * 30),
	]
	passages = _build(messages, target=80, overlap=30)
	assert len(passages) == 2
	second = passages[1]
	assert "beta " in second.text
	assert second.anchor_message_id == "m3"


def test_empty_and_non_text_threads_produce_no_passages() -> None:
	assert _build([]) == []
	messages = [_msg("m1", None, MessageType.TOOL, "tool only")]
	assert _build(messages) == []


def test_passage_type() -> None:
	messages = [_msg("m1", None, MessageType.USER, "hello world")]
	passages = _build(messages)
	assert isinstance(passages[0], TranscriptPassage)
