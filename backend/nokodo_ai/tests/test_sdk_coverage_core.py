"""coverage-driven tests for SDK core utilities and models."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal, cast

import pytest

from nokodo_ai.chat_models import ChatModel
from nokodo_ai.deltas import (
	stream_agent_deltas,
	stream_chat_model_deltas,
)
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.filters import Filter
from nokodo_ai.hooks import Hook
from nokodo_ai.messages import (
	AssistantMessage,
	JsonContent,
	TextContent,
	ToolCall,
	ToolMessage,
	Usage,
	UserMessage,
)
from nokodo_ai.thread import Thread
from nokodo_ai.utils.json_schema import schema_from_callable
from nokodo_ai.utils.validators import (
	types_compatible,
	validate,
	validate_callable,
	validate_literal,
)


def test_validate_literal_success_and_errors() -> None:
	assert validate_literal("a", cast(Any, Literal["a", "b"])) == "a"
	with pytest.raises(TypeError, match="at least one literal"):
		validate_literal("a", cast(Any, Literal))
	with pytest.raises(TypeError, match="literal_type must be"):
		validate_literal("a", str)
	with pytest.raises(ValueError, match="invalid value"):
		validate_literal("c", cast(Any, Literal["a", "b"]))


def test_validate_covers_union_annotated_none_and_pydantic_paths() -> None:
	assert validate(None, None) is None
	with pytest.raises(TypeError, match="expected None"):
		validate("x", None)

	t = Annotated[int, "x"]
	assert validate(1, t) == 1

	u = int | str
	assert validate(1, u) == 1
	assert validate("a", u) == "a"
	with pytest.raises(TypeError, match="expected type"):
		validate([], u)

	assert validate("a", Literal["a"]) == "a"

	# isinstance path
	assert validate("x", str) == "x"
	with pytest.raises(TypeError, match="expected type"):
		validate(1, str)

	# pydantic validation path for complex types
	assert validate([1, 2], list[int]) == [1, 2]
	with pytest.raises(Exception):
		validate(["a"], list[int])


def test_types_compatible_branches() -> None:
	assert types_compatible(int, int)
	assert types_compatible(list[int], list)
	assert types_compatible(list[int], list[int])
	assert types_compatible(list[int], list[str]) is True
	assert types_compatible(list[int], dict[str, int]) is False
	assert types_compatible(bool, int)

	from abc import ABCMeta

	class _BoomMeta(ABCMeta):
		def __subclasscheck__(cls, subclass):
			raise TypeError("boom")

	class _Boom(metaclass=_BoomMeta):
		pass

	assert types_compatible(int, _Boom) is False
	assert types_compatible("x", int) is False


def test_validate_callable_success_and_failure_modes() -> None:
	def ok(a: int, b: str) -> int:
		_ = b
		return a

	validate_callable(
		ok,
		expected_arg_types=[int, str],
		expected_return_type=int,
		expected_arg_names=["a", "b"],
		expected_arg_count={"min": 2, "max": 2},
	)

	def too_few(a: int) -> int:
		return a

	with pytest.raises(TypeError, match="expected at least"):
		validate_callable(too_few, expected_arg_count={"min": 2, "max": None})

	def too_many(a: int, b: int, c: int) -> int:
		return a + b + c

	with pytest.raises(TypeError, match="expected at most"):
		validate_callable(too_many, expected_arg_count={"min": 0, "max": 2})

	with pytest.raises(TypeError, match="missing parameter"):
		validate_callable(ok, expected_arg_names=["a", "b", "c"])

	with pytest.raises(TypeError, match="must be named"):
		validate_callable(ok, expected_arg_names=["x", "b"])

	def missing_anno(a, b: int) -> int:
		return b

	with pytest.raises(TypeError, match="missing type annotation"):
		validate_callable(missing_anno, expected_arg_types=[int, int])

	with pytest.raises(TypeError, match="has type"):
		validate_callable(ok, expected_arg_types=[str, str])

	def missing_return(a: int):
		return a

	with pytest.raises(TypeError, match="missing return type"):
		validate_callable(missing_return, expected_return_type=int)

	def wrong_return(a: int) -> str:
		return str(a)

	with pytest.raises(TypeError, match="return type is"):
		validate_callable(wrong_return, expected_return_type=int)

	with pytest.raises(TypeError, match="missing parameter at position"):
		validate_callable(ok, expected_arg_types=[int, str, int])

	def _bad_forward_ref(a):
		return a

	_bad_forward_ref.__annotations__ = {"a": "NoSuchType", "return": "NoSuchType"}
	validate_callable(_bad_forward_ref, expected_arg_count={"min": 1, "max": 1})


def test_schema_from_callable_skips_self_dunder_and_varargs() -> None:
	class X:
		def f(
			self,
			a: int,
			b: str = "x",
			__agent_context__: object | None = None,
			*args: object,
			**kwargs: object,
		):
			_ = (a, b, __agent_context__, args, kwargs)

	schema = schema_from_callable(X.f)
	assert "properties" in schema
	props = schema.get("properties")
	assert isinstance(props, dict)
	assert "a" in props
	assert "b" in props
	assert "__agent_context__" not in props

	schema2 = schema_from_callable(X.f, skip_fields={"b"})
	props2 = schema2.get("properties") or {}
	assert isinstance(props2, dict)
	assert "b" not in props2

	def empty() -> None:
		return None

	assert schema_from_callable(empty) == {}


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
	for item in items:
		yield item


@pytest.mark.asyncio
async def test_stream_deltas_cover_all_branches() -> None:
	chat_stream = _aiter(
		[AssistantMessage.from_text("a"), AssistantMessage.from_text("b")]
	)
	seen = []
	async for d in stream_chat_model_deltas(chat_stream):
		seen.append(d)
	assert seen[-1].done is True

	agent_stream = _aiter(
		[
			ToolMessage(tool_call_id="t1", tool_output="ok"),
			AssistantMessage.from_text("done"),
		]
	)
	seen2 = []
	async for d in stream_agent_deltas(agent_stream):
		seen2.append(d)
	assert seen2[-1].done is True
	assert any(x.tool is not None for x in seen2)
	assert any(x.chat is not None for x in seen2)

	bad_stream = _aiter([UserMessage.from_text("x")])
	with pytest.raises(TypeError, match="unsupported agent stream"):
		async for _ in stream_agent_deltas(bad_stream):
			pass


def test_assistant_message_merge_covers_tool_usage_and_metadata() -> None:
	base = AssistantMessage(content=[TextContent(text="a")])
	base.tool_calls = [ToolCall(id="tc1", name="t", arguments="{")]
	base.usage = Usage(input_tokens=1, output_tokens=1, total_tokens=2)
	base.metadata = {"a": 1}

	delta = AssistantMessage(content=[TextContent(text="b")])
	delta.tool_calls = [ToolCall(id="tc1", name="t", arguments="}")]
	delta.usage = Usage(input_tokens=1, output_tokens=2, total_tokens=3)
	delta.finish_reason = "stop"
	delta.metadata = {"b": 2}

	base.merge(delta)
	assert base.text == "ab"
	assert base.tool_calls[0].arguments == "{}"
	assert base.usage.total_tokens == 5
	assert base.finish_reason == "stop"
	assert base.metadata == {"a": 1, "b": 2}

	# json helper
	base.content.append(JsonContent(data={"x": 1}))
	assert base.json == {"x": 1}


def test_assistant_message_merge_additional_branches() -> None:
	base = AssistantMessage.from_text("")
	base.tool_calls = [ToolCall(id="tc1", name="", arguments="")]
	base.metadata = None
	base.usage = None

	delta = AssistantMessage.from_text("")
	delta.content = [JsonContent(data={"x": 1})]
	delta.tool_calls = [
		ToolCall(id="tc1", name="t", arguments={"a": 1}),
		ToolCall(id="tc2", name="t2", arguments="{}"),
	]
	delta.metadata = {"k": "v"}
	delta.usage = Usage(input_tokens=1, output_tokens=2, total_tokens=3)

	base.merge(delta)
	assert base.tool_calls[0].arguments == {"a": 1}
	assert base.tool_calls[0].name == "t"
	assert any(tc.id == "tc2" for tc in base.tool_calls)
	assert base.metadata == {"k": "v"}
	assert base.usage == Usage(input_tokens=1, output_tokens=2, total_tokens=3)


def test_assistant_message_merge_skips_empty_delta_name_and_args() -> None:
	base = AssistantMessage.from_text("")
	base.tool_calls = [ToolCall(id="tc1", name="t", arguments={"a": 1})]

	delta = AssistantMessage.from_text("")
	# arguments is falsy and name is empty, so merge should not change them
	delta.tool_calls = [ToolCall(id="tc1", name="", arguments=None)]

	base.merge(delta)
	assert base.tool_calls[0].arguments == {"a": 1}
	assert base.tool_calls[0].name == "t"


def test_chat_model_resolve_adapter_config_and_init_branches(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# unknown provider
	with pytest.raises(ValueError, match="unknown provider"):
		ChatModel.model_validate({"model_name": "weird:thing"})

	# no adapter specified -> auto config (use ollama to avoid client initialization)
	m = ChatModel.model_validate({"model_name": "ollama:llama"})
	assert m.provider == "ollama"
	assert m.adapter.type == "ollama.chat"

	# adapter shorthand expanded to fully qualified type
	from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter

	monkeypatch.setattr(BaseOpenAIAdapter, "_get_client", lambda self: object())
	m2 = ChatModel.model_validate(
		{
			"model_name": "openai:gpt-4o",
			"adapter": {"type": "openai"},
		}
	)
	assert m2.adapter.type.startswith("openai.")

	# cover adapter shorthand resolution when provider isn't supplied by model_name
	m3 = ChatModel.model_validate(
		{
			"model_name": "gpt-4o",
			"adapter": {"type": "openai"},
		}
	)
	assert m3.adapter.type.startswith("openai.")

	# adapter already fully-qualified (contains a dot) should not be expanded
	from nokodo_ai.adapters.chat import resolve_chat_adapter

	adapter_type = resolve_chat_adapter("openai", None)
	assert adapter_type is not None and "." in adapter_type
	m4 = ChatModel.model_validate(
		{
			"model_name": "openai:gpt-4o",
			"adapter": {"type": adapter_type},
		}
	)
	assert m4.adapter.type == adapter_type

	with pytest.raises(Exception):
		ChatModel.model_validate("x")
	with pytest.raises(Exception):
		ChatModel.model_validate({"model_name": ""})

	# cover the shorthand-adapter unknown provider branch (chat_models.py line 62)
	import nokodo_ai.chat_models as cm

	monkeypatch.setattr(cm, "resolve_chat_adapter", lambda provider, adapter: None)
	with pytest.raises(ValueError, match="unknown provider"):
		ChatModel.model_validate(
			{
				"model_name": "gpt-4o",
				"adapter": {"type": "openai"},
			}
		)


def test_embedding_model_resolve_adapter_config_unknown_and_ok() -> None:
	with pytest.raises(ValueError, match="unknown embedding provider"):
		EmbeddingModel.model_validate({"model": "weird:thing"})

	emb = EmbeddingModel.model_validate({"model": "ollama:embed"})
	assert emb.provider == "ollama"
	assert emb.adapter.type == "ollama.embedding"

	emb2 = EmbeddingModel.model_validate(
		{
			"adapter": {"type": "ollama.embedding"},
			"model_name": "m",
		}
	)
	assert emb2.adapter.type == "ollama.embedding"

	with pytest.raises(Exception):
		EmbeddingModel.model_validate({"provider": "", "model_name": "m"})

	# non-dict input passes through unchanged
	assert cast(Any, EmbeddingModel).resolve_adapter_config("x") == "x"


@pytest.mark.asyncio
async def test_filters_and_hooks_not_implemented_raise_async() -> None:
	class MyFilter(Filter[None]):
		async def process(self, thread: Thread, app_context: None) -> Thread:
			return await cast(Any, super()).process(thread, app_context)

	class MyHook(Hook[None]):
		async def execute(self, thread: Thread, app_context: None) -> None:
			return await cast(Any, super()).execute(thread, app_context)

	f = MyFilter(name="f")
	h = MyHook(name="h")

	with pytest.raises(NotImplementedError, match="process method must be"):
		await f.process(Thread(), None)

	with pytest.raises(NotImplementedError, match="execute method must be"):
		await h.execute(Thread(), None)
