from __future__ import annotations

from api.settings.settings import AIAttachmentSettings
from api.v1.service.chat.context_compaction.media import (
	_DECAY_MARKER,
	MEDIA_PROTECTED_METADATA_KEY,
	_MediaOccurrence,
	compute_iteration_indices,
	compute_turn_indices,
	project_attachments,
)
from api.v1.service.chat.message_metadata import SENDER_USER_ID_KEY
from api.v1.service.files.modalities import classify_media, modality_supported
from nokodo_ai.messages import (
	AssistantMessage,
	FileContent,
	ImageContent,
	TextContent,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.utils.typeid import TypeID


def _occ(**kwargs: object) -> _MediaOccurrence:
	defaults: dict[str, object] = {
		"file_id": TypeID("file_123"),
		"message_index": 0,
		"part_index": 0,
		"turn": 0,
		"iteration": 0,
		"on_tool_message": False,
		"media_type": "image/png",
		"filename": None,
		"description": None,
		"content_type": "image",
	}
	defaults.update(kwargs)
	return _MediaOccurrence(**defaults)  # type: ignore[arg-type]


def test_decay_marker_is_payload_free() -> None:
	assert _DECAY_MARKER == "[native media attachment unloaded]"


def test_classify_media() -> None:
	assert classify_media("image/png") == "image"
	assert classify_media("audio/mpeg") == "audio"
	assert classify_media("video/mp4") == "video"
	assert classify_media("application/pdf") == "other"
	assert classify_media(None) == "other"


def test_modality_supported_fails_open_when_unknown() -> None:
	assert modality_supported("image/png", None) is True


def test_modality_supported_respects_model_capabilities() -> None:
	assert modality_supported("image/png", {"text", "images"}) is True
	assert modality_supported("image/png", {"text"}) is False
	# non-media types are always allowed (returned as derived text)
	assert modality_supported("application/pdf", {"text"}) is True


def test_project_media_renders_user_media_as_reference() -> None:
	user = UserMessage(
		content=[
			ImageContent(
				filename="photo.png",
				media_type="image/png",
				metadata={"file_id": "file_abc"},
			),
			TextContent(text="what is this?"),
		]
	)

	projection = project_attachments([user], {"images"}, AIAttachmentSettings())

	new_user = projection.messages[0]
	assert isinstance(new_user.content[0], TextContent)
	# natively attached media is released to an id-bearing marker: nothing else
	# in the thread names it, so the marker carries the file id.
	marker = new_user.content[0].text
	assert marker.startswith("[native media attachment unloaded")
	assert "file_abc" in marker


def test_project_media_protects_active_tool_media() -> None:
	tool = ToolMessage(
		tool_call_id="call_1",
		tool_output="retrieved",
		attachments=[
			ImageContent(
				filename="photo.png",
				media_type="image/png",
				metadata={"file_id": "file_abc", "fetched": True},
			)
		],
	)

	projection = project_attachments([tool], {"images"}, AIAttachmentSettings())

	new_tool = projection.messages[0]
	assert new_tool.metadata is not None
	assert new_tool.metadata.get(MEDIA_PROTECTED_METADATA_KEY) is True
	assert len(new_tool.attachments) == 1


def test_project_media_hard_protects_media_at_the_consuming_call() -> None:
	# the real agentic shape: within ONE user turn the model emits a tool_call,
	# the tool appends bytes, then the model is called AGAIN to read them. at
	# that consuming call the thread ends with the byte-carrying tool message.
	# the hard window must cover this exact moment (the off-by-one risk: the
	# window expiring on the append turn, before the read).
	from nokodo_ai.messages import ToolCall

	consuming_call_thread = [
		UserMessage(content=[TextContent(text="show me the diagram")]),
		AssistantMessage(
			content=[TextContent(text="fetching")],
			tool_calls=[ToolCall(id="call_1", name="file_get", arguments="{}")],
		),
		ToolMessage(
			tool_call_id="call_1",
			tool_output="retrieved",
			attachments=[
				ImageContent(
					filename="d.png",
					media_type="image/png",
					metadata={"file_id": "file_abc", "fetched": True},
				)
			],
		),
	]

	projection = project_attachments(
		consuming_call_thread, {"images"}, AIAttachmentSettings()
	)

	tool_msg = projection.messages[2]
	# bytes are still attached AND hard-protected when the model reads them
	assert len(tool_msg.attachments) == 1
	assert (tool_msg.metadata or {}).get(MEDIA_PROTECTED_METADATA_KEY) is True


def _img(file_id: str, **meta: object) -> ImageContent:
	return ImageContent(
		filename="photo.png",
		media_type="image/png",
		metadata={"file_id": file_id, "fetched": True, **meta},
	)


def test_project_media_soft_media_stays_native_but_unmarked() -> None:
	# within ONE agent turn the model fetches twice across iterations. the
	# earlier fetch is still inside the soft image window (3 iterations) but past
	# the hard window (the read iteration), so its bytes stay native but unmarked.
	messages = [
		_turn_user("analyze these"),  # turn 0
		_turn_assistant("fetching the first"),  # turn 1, iteration 1
		_tool_with(_img("file_old"), call_id="call_old"),  # turn 1, iteration 1
		_turn_assistant("now the second"),  # turn 1, iteration 2
		_tool_with(_img("file_new"), call_id="call_new"),  # turn 1, iteration 2
	]

	projection = project_attachments(messages, {"images"}, AIAttachmentSettings())

	soft = projection.messages[2]
	hard = projection.messages[4]
	# soft media: still native, but not hard-protected (read iteration passed)
	assert len(soft.attachments) == 1
	assert not (soft.metadata or {}).get(MEDIA_PROTECTED_METADATA_KEY)
	# the newest fetch is the read iteration (distance 0) and is marked
	assert (hard.metadata or {}).get(MEDIA_PROTECTED_METADATA_KEY) is True


def test_project_media_keeps_distinct_renditions_of_mutable_file() -> None:
	# same file_id fetched twice with different updated_at = different content.
	# the older rendition must not be silently dropped as a duplicate.
	first = ToolMessage(
		tool_call_id="c1",
		tool_output="r",
		attachments=[_img("file_x", updated_at="2026-01-01T00:00:00+00:00")],
	)
	second = ToolMessage(
		tool_call_id="c2",
		tool_output="r",
		attachments=[_img("file_x", updated_at="2026-02-01T00:00:00+00:00")],
	)

	projection = project_attachments(
		[first, second], {"images"}, AIAttachmentSettings()
	)

	assert len(projection.messages[0].attachments) == 1
	assert len(projection.messages[1].attachments) == 1


def test_project_media_drops_superseded_same_version_copy() -> None:
	# same file_id, same content signature: the older copy is a true duplicate.
	first = ToolMessage(
		tool_call_id="c1",
		tool_output="r",
		attachments=[_img("file_y", updated_at="2026-01-01T00:00:00+00:00")],
	)
	second = ToolMessage(
		tool_call_id="c2",
		tool_output="r",
		attachments=[_img("file_y", updated_at="2026-01-01T00:00:00+00:00")],
	)

	projection = project_attachments(
		[first, second], {"images"}, AIAttachmentSettings()
	)

	assert len(projection.messages[0].attachments) == 0
	assert len(projection.messages[1].attachments) == 1


# -- scenario helpers: multi-turn threads with media injected over time --


def _vid(file_id: str, **meta: object) -> FileContent:
	return FileContent(
		filename="clip.mp4",
		media_type="video/mp4",
		metadata={"file_id": file_id, "fetched": True, **meta},
	)


def _turn_user(text: str) -> UserMessage:
	return UserMessage(content=[TextContent(text=text)])


def _turn_assistant(text: str) -> AssistantMessage:
	return AssistantMessage(content=[TextContent(text=text)])


def _tool_with(*attachments: object, call_id: str = "call") -> ToolMessage:
	return ToolMessage(
		tool_call_id=call_id,
		tool_output="retrieved",
		attachments=list(attachments),  # type: ignore[arg-type]
	)


def _has_decay_marker(message: object) -> bool:
	"""check whether a message carries the inline decay marker."""
	if isinstance(message, ToolMessage):
		return _DECAY_MARKER in message.tool_output
	for part in getattr(message, "content", []):
		if isinstance(part, TextContent) and _DECAY_MARKER in part.text:
			return True
	return False


def test_project_media_releases_media_past_soft_window() -> None:
	# media fetched in an earlier agent turn is released regardless of iteration
	# count: protection only lives inside the current agent turn. bytes are
	# stripped and an inline decay marker is prepended (recoverable via
	# file_get).
	messages = [
		_turn_user("t0"),  # turn 0
		_turn_assistant("a0"),  # turn 1
		_tool_with(_img("file_old")),  # turn 1
		_turn_user("t1"),  # turn 2 (ball back to the user)
		_turn_assistant("a1"),  # turn 3 (a new agent turn)
	]

	projection = project_attachments(messages, {"images"}, AIAttachmentSettings())

	assert len(projection.messages[2].attachments) == 0
	assert TypeID("file_old") in projection.newly_released
	assert _has_decay_marker(projection.messages[2])


def test_project_media_releases_modality_unsupported() -> None:
	# the model has no image modality: even in the hard window the image cannot
	# be shown natively, so it is released to an unload marker, unmarked.
	tool = _tool_with(_img("file_img"))

	projection = project_attachments([tool], {"text"}, AIAttachmentSettings())

	new_tool = projection.messages[0]
	assert len(new_tool.attachments) == 0
	assert not (new_tool.metadata or {}).get(MEDIA_PROTECTED_METADATA_KEY)
	assert _has_decay_marker(new_tool)


def test_project_media_video_window_shorter_than_image() -> None:
	# video soft window is 1 iteration (read-only), image is 3. both are fetched
	# one iteration ago within the same agent turn: the video has aged out while
	# the image survives.
	messages = [
		_turn_user("look at both"),  # turn 0
		_turn_assistant("fetching"),  # turn 1, iteration 1
		_tool_with(_vid("file_v"), _img("file_i")),  # turn 1, iteration 1
		_turn_assistant("analysis"),  # turn 1, iteration 2
	]

	projection = project_attachments(
		messages, {"images", "video"}, AIAttachmentSettings()
	)

	tool = projection.messages[2]
	kept_ids = {(a.metadata or {}).get("file_id") for a in tool.attachments}
	assert "file_i" in kept_ids
	assert "file_v" not in kept_ids


def test_project_media_manifest_marks_active_soft_and_released() -> None:
	# one released (fetched in an earlier agent turn), plus one soft and one hard
	# in the CURRENT agent turn at different iterations. the manifest reports
	# active for both live ones and released for the aged one.
	messages = [
		_turn_user("t0"),  # turn 0
		_turn_assistant("a0"),  # turn 1, iteration 1
		_tool_with(_img("file_aged"), call_id="c0"),  # turn 1, iteration 1
		_turn_assistant("a0b"),  # turn 1, iteration 2
		_turn_user("t1"),  # turn 2 (ball back to user)
		_turn_assistant("a1"),  # turn 3, iteration 1
		_tool_with(_img("file_soft"), call_id="c1"),  # turn 3, iteration 1
		_turn_assistant("a1b"),  # turn 3, iteration 2
		_tool_with(_img("file_hard"), call_id="c2"),  # turn 3, iteration 2
	]

	projection = project_attachments(messages, {"images"}, AIAttachmentSettings())

	# file_aged was fetched in a previous agent turn -> released to a marker
	assert len(projection.messages[2].attachments) == 0
	assert _has_decay_marker(projection.messages[2])
	assert TypeID("file_aged") in projection.newly_released
	# file_soft is in the current turn, one iteration back -> still native
	assert len(projection.messages[6].attachments) == 1
	assert TypeID("file_soft") not in projection.newly_released
	# file_hard is the read iteration of the current turn -> native
	assert len(projection.messages[8].attachments) == 1
	assert TypeID("file_hard") not in projection.newly_released
	# the soft (earlier-iteration) message must NOT carry the protection marker
	assert not (projection.messages[6].metadata or {}).get(MEDIA_PROTECTED_METADATA_KEY)
	# only the hard (read-iteration) message carries the protection marker
	assert (projection.messages[8].metadata or {}).get(MEDIA_PROTECTED_METADATA_KEY)


def test_project_media_renders_many_user_attachments_as_markers() -> None:
	# all user-attached images become inline decay markers, none stay native.
	content: list[object] = []
	for i in range(60):
		content.append(
			ImageContent(
				filename=f"f{i}.png",
				media_type="image/png",
				metadata={"file_id": f"file_{i}"},
			)
		)
	user = UserMessage(content=content)  # type: ignore[arg-type]

	projection = project_attachments([user], {"images"}, AIAttachmentSettings())

	new_user = projection.messages[0]
	# every user-attached image becomes an inline id-bearing marker, none native.
	assert len(new_user.content) == 60
	assert all(isinstance(part, TextContent) for part in new_user.content)
	for i, part in enumerate(new_user.content):
		assert isinstance(part, TextContent)
		assert f"file_{i}" in part.text


def test_project_media_releases_in_turn_image_past_soft_window() -> None:
	# image soft window is 3 iterations counting the read. fetched at iteration 1
	# of an agent turn that then runs to iteration 4 (distance 3) WITHOUT the
	# ball returning to the user: the image ages out inside the same agent turn.
	messages = [
		_turn_user("look at this"),  # turn 0
		_turn_assistant("fetching"),  # turn 1, iteration 1
		_tool_with(_img("file_i"), call_id="c0"),  # turn 1, iteration 1
		_turn_assistant("step 2"),  # turn 1, iteration 2
		_turn_assistant("step 3"),  # turn 1, iteration 3
		_turn_assistant("step 4"),  # turn 1, iteration 4 (distance 3)
	]

	projection = project_attachments(messages, {"images"}, AIAttachmentSettings())

	tool = projection.messages[2]
	# distance 3 == image window 3 -> aged out, bytes stripped and released
	assert len(tool.attachments) == 0
	assert TypeID("file_i") in projection.newly_released
	assert _has_decay_marker(tool)


def test_project_media_keeps_in_turn_image_at_window_edge() -> None:
	# the same shape one iteration earlier (distance 2 < window 3): still native.
	messages = [
		_turn_user("look at this"),  # turn 0
		_turn_assistant("fetching"),  # turn 1, iteration 1
		_tool_with(_img("file_i"), call_id="c0"),  # turn 1, iteration 1
		_turn_assistant("step 2"),  # turn 1, iteration 2
		_turn_assistant("step 3"),  # turn 1, iteration 3 (distance 2)
	]

	projection = project_attachments(messages, {"images"}, AIAttachmentSettings())

	tool = projection.messages[2]
	assert len(tool.attachments) == 1
	assert TypeID("file_i") not in projection.newly_released


# -- turn / iteration index math (the subtlest logic, tested in isolation) --


def test_compute_turn_indices_groups_agent_run_as_one_turn() -> None:
	# one user turn, then a whole agent run (assistant + tool + assistant) is a
	# single turn, then the ball returns to the user, then a new agent turn.
	messages = [
		UserMessage(content=[TextContent(text="q")]),
		AssistantMessage(content=[TextContent(text="a")]),
		ToolMessage(tool_call_id="c", tool_output="o", attachments=[]),
		AssistantMessage(content=[TextContent(text="a2")]),
		UserMessage(content=[TextContent(text="q2")]),
		AssistantMessage(content=[TextContent(text="a3")]),
	]

	assert compute_turn_indices(messages) == [0, 1, 1, 1, 2, 3]


def test_compute_turn_indices_folds_system_messages() -> None:
	# a leading system message folds into the first turn; a mid-thread system
	# message folds into the turn in progress and does not advance the counter.
	from nokodo_ai.messages import SystemMessage

	messages = [
		SystemMessage(content=[TextContent(text="sys")]),
		UserMessage(content=[TextContent(text="q")]),
		SystemMessage(content=[TextContent(text="sys2")]),
		AssistantMessage(content=[TextContent(text="a")]),
	]

	assert compute_turn_indices(messages) == [0, 0, 0, 1]


def test_compute_turn_indices_splits_consecutive_users_by_sender() -> None:
	# in a group thread, back-to-back user messages from different senders are
	# distinct turns; same sender stays one turn.
	messages = [
		UserMessage(
			content=[TextContent(text="a")], metadata={SENDER_USER_ID_KEY: "u1"}
		),
		UserMessage(
			content=[TextContent(text="b")], metadata={SENDER_USER_ID_KEY: "u2"}
		),
		UserMessage(
			content=[TextContent(text="c")], metadata={SENDER_USER_ID_KEY: "u2"}
		),
	]

	assert compute_turn_indices(messages) == [0, 1, 1]


def test_compute_iteration_indices_increments_per_assistant_message() -> None:
	# inside one agent turn each assistant message is a new iteration; a tool
	# message inherits its caller's iteration.
	messages = [
		UserMessage(content=[TextContent(text="q")]),
		AssistantMessage(content=[TextContent(text="a")]),
		ToolMessage(tool_call_id="c1", tool_output="o", attachments=[]),
		AssistantMessage(content=[TextContent(text="a2")]),
		ToolMessage(tool_call_id="c2", tool_output="o", attachments=[]),
	]

	assert compute_iteration_indices(messages) == [0, 1, 1, 2, 2]


def test_compute_iteration_indices_resets_each_agent_turn() -> None:
	# the iteration counter resets to 0 at the start of every agent turn, so
	# iterations are only comparable within the same turn.
	messages = [
		UserMessage(content=[TextContent(text="q")]),
		AssistantMessage(content=[TextContent(text="a")]),
		UserMessage(content=[TextContent(text="q2")]),
		AssistantMessage(content=[TextContent(text="a2")]),
		AssistantMessage(content=[TextContent(text="a3")]),
	]

	assert compute_iteration_indices(messages) == [0, 1, 0, 1, 2]
