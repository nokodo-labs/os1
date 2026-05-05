"""agentic web search service."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import perplexity as perplexity_sdk
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.models.access_rule import AccessLevel
from api.models.agent import Agent as AgentORM
from api.models.model import Model
from api.permissions import ResourceType
from api.perplexity import PerplexityClient
from api.schemas.citations import Citation, CitationSource
from api.settings import SearchAgent, SearchEngine, SearchRecencyFilter, settings
from api.v1.schemas.web_search import (
	AgenticWebSearchResult,
	WebSearchImage,
	WebSearchSource,
)
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.models import (
	build_chat_model,
	resolve_model_for_run,
	resolve_task_chat_model,
)
from api.v1.service.chat.tools.web_search import WebSearchTool
from nokodo_ai.agents import Agent as SDKAgent
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.messages import (
	AssistantMessage,
	SystemMessage,
	ToolCall,
	ToolMessage,
	UserMessage,
)
from nokodo_ai.threads import Thread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID

from .errors import WebSearchError
from .progress import build_agentic_web_search_progress
from .search import is_blacklisted


logger = logging.getLogger(__name__)


type AgenticWebSearchProgressCallback = Callable[[str, JSONObject], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class NativeAgenticWebSearchConfig:
	chat_model: ChatModel
	system_prompt: str
	max_iterations: int


async def search_agentic_web(
	query: str,
	limit: int | None = None,
	include_images: bool | None = None,
	search_recency_filter: SearchRecencyFilter | None = None,
	search_agent: SearchAgent | None = None,
	agent_id_override: TypeID | None = None,
	app_context: AppContext | None = None,
	progress_callback: AgenticWebSearchProgressCallback | None = None,
) -> AgenticWebSearchResult:
	"""perform agentic web search using the configured search agent."""
	agentic_settings = settings.web_search.agentic
	agent = search_agent or agentic_settings.agent
	if agent == "perplexity":
		return await _search_perplexity_agent(
			query,
			limit=limit,
			include_images=include_images,
			search_recency_filter=search_recency_filter,
		)
	if agent == "native":
		if include_images:
			raise WebSearchError("images are not supported by native web search")
		return await _search_native_agent(
			query,
			limit=limit,
			agent_id_override=agent_id_override,
			search_recency_filter=search_recency_filter,
			app_context=app_context,
			progress_callback=progress_callback,
		)
	raise WebSearchError(f"unsupported search agent: {agent}")


async def _search_perplexity_agent(
	query: str,
	limit: int | None,
	include_images: bool | None,
	search_recency_filter: SearchRecencyFilter | None,
) -> AgenticWebSearchResult:
	"""run the Perplexity agentic search path and normalize its response."""
	pplx = settings.integrations.perplexity
	ws = settings.web_search
	if not pplx.api_key:
		raise WebSearchError("perplexity search agent is not configured")
	return_images = bool(include_images and pplx.image_results_enabled)

	client = PerplexityClient(api_key=pplx.api_key)
	try:
		result = await client.agentic_search(
			query,
			model=pplx.model,
			system_prompt=ws.agentic.system_prompt,
			temperature=pplx.temperature,
			search_context_usage=pplx.search_context_usage,
			search_recency_filter=search_recency_filter,
			return_images=return_images,
			max_results=limit,
		)
	except perplexity_sdk.APIStatusError as exc:
		logger.error(
			"perplexity API error %s: %s",
			exc.status_code,
			str(exc.message)[:200],
		)
		raise WebSearchError(f"perplexity API error: {exc.status_code}") from exc
	except perplexity_sdk.APIConnectionError as exc:
		logger.error("perplexity request failed: %s", exc)
		raise WebSearchError("perplexity request failed") from exc

	filtered = [
		source
		for source in result.results
		if not is_blacklisted(source.url, ws.blacklisted_domains)
	]
	images = [
		WebSearchImage(url=image.url, title=image.title, source_url=image.source_url)
		for image in result.images
		if not is_blacklisted(image.source_url or image.url, ws.blacklisted_domains)
	]

	return AgenticWebSearchResult(
		summary=result.content,
		citations=[
			Citation(
				index=index,
				source_type=CitationSource.URL,
				source_id=source.url,
				title=source.title,
			)
			for index, source in enumerate(filtered, 1)
		],
		images=images,
		agent="perplexity",
		engine="perplexity",
	)


async def _search_native_agent(
	query: str,
	limit: int | None,
	agent_id_override: TypeID | None,
	search_recency_filter: SearchRecencyFilter | None,
	app_context: AppContext | None,
	progress_callback: AgenticWebSearchProgressCallback | None = None,
) -> AgenticWebSearchResult:
	"""run the native SDK agent and collect its web_search tool outputs."""
	if app_context is None:
		raise WebSearchError("app context is required for native web search")

	config = await _resolve_native_agentic_config(app_context, agent_id_override)
	agent = SDKAgent[AppContext](
		chat_model=config.chat_model,
		tools=[
			WebSearchTool(
				default_limit=limit,
				default_search_recency_filter=search_recency_filter,
			)
		],
		max_iterations=config.max_iterations,
	)
	thread = Thread()
	thread.add(SystemMessage.from_text(config.system_prompt))
	thread.add(UserMessage.from_text(f"search query:\n{query}"))
	stream = await agent.run(
		thread,
		app_context=app_context,
		tool_choice="auto",
		stream=True,
	)
	produced: list[AssistantMessage | ToolMessage] = []
	search_queries_by_call: dict[str, str] = {}
	assistant_accum: AssistantMessage | None = None
	async for delta in stream:
		if delta.chat is not None:
			if assistant_accum is None:
				assistant_accum = AssistantMessage()
			assistant_accum = assistant_accum.merge(delta.chat.message)
			await _emit_started_searches(
				query,
				assistant_accum.tool_calls,
				search_queries_by_call,
				progress_callback,
			)
			if delta.chat.done:
				if assistant_accum.text.strip() or assistant_accum.tool_calls:
					produced.append(assistant_accum)
				assistant_accum = None

		if delta.tool is not None:
			produced.append(delta.tool)
			await _emit_tool_result_progress(
				query,
				delta.tool,
				search_queries_by_call,
				progress_callback,
			)

	sources = _collect_web_search_sources(produced)
	engine = _collect_engine(produced)
	summary = _last_assistant_text(produced)
	if not summary:
		summary = "native web search did not return a synthesized answer."
	await _emit_progress(
		progress_callback,
		f"found {len(sources)} resources",
		build_agentic_web_search_progress(
			stage="completed",
			message=f"found {len(sources)} resources",
			query=query,
			agent="native",
			engine=engine,
			result_count=len(sources),
			sources=sources,
		),
	)

	return AgenticWebSearchResult(
		summary=summary,
		citations=[
			Citation(
				index=index,
				source_type=CitationSource.URL,
				source_id=source.url,
				title=source.title,
			)
			for index, source in enumerate(sources, 1)
		],
		agent="native",
		engine=engine,
	)


async def _resolve_native_agentic_config(
	app_context: AppContext,
	agent_id_override: TypeID | None,
) -> NativeAgenticWebSearchConfig:
	"""resolve the model, prompt, and iteration budget for native search."""
	agentic_settings = settings.web_search.agentic
	if agent_id_override is None:
		try:
			if agentic_settings.model_id:
				model = await resolve_model_for_run(
					app_context.session,
					model=agentic_settings.model_id,
				)
				chat_model = build_chat_model(
					model,
					params=agentic_settings.model_params,
				)
			else:
				chat_model = await resolve_task_chat_model(
					app_context.session,
					"web_search",
				)
		except Exception as exc:
			raise WebSearchError("native search agent model is not configured") from exc
		return NativeAgenticWebSearchConfig(
			chat_model=chat_model,
			system_prompt=agentic_settings.system_prompt,
			max_iterations=agentic_settings.max_iterations,
		)

	agent = await _load_search_agent(app_context, agent_id_override)
	if agent.model is None:
		raise WebSearchError("native search agent has no model configured")

	chat_model_config: dict[str, object] | None = None
	raw_chat_model_config = (agent.config or {}).get("chat_model")
	if raw_chat_model_config is not None:
		if not isinstance(raw_chat_model_config, dict):
			raise WebSearchError(
				"native search agent chat_model config must be an object"
			)
		chat_model_config = {
			str(key): value for key, value in raw_chat_model_config.items()
		}
	max_iterations = agentic_settings.max_iterations
	configured_iterations = (agent.config or {}).get("max_iterations")
	if isinstance(configured_iterations, int):
		max_iterations = configured_iterations
	system_prompt = agentic_settings.system_prompt
	if agent.system_prompt:
		system_prompt = (
			f"{system_prompt}\n\nadditional search agent instructions:\n"
			f"{agent.system_prompt}"
		)

	return NativeAgenticWebSearchConfig(
		chat_model=build_chat_model(agent.model, params=chat_model_config),
		system_prompt=system_prompt,
		max_iterations=max_iterations,
	)


async def _load_search_agent(
	app_context: AppContext,
	agent_id: TypeID,
) -> AgentORM:
	"""load a user-visible agent to use as the native search agent."""
	stmt = (
		select(AgentORM)
		.options(selectinload(AgentORM.model).selectinload(Model.provider))
		.where(
			AgentORM.id == agent_id,
			resource_access_predicate(
				app_context.principal,
				ResourceType.AGENT,
				required_level=AccessLevel.READER,
			),
		)
	)
	result = await app_context.session.execute(stmt)
	agent = result.scalars().one_or_none()
	if agent is None:
		raise WebSearchError("native search agent not found")
	return agent


async def _emit_started_searches(
	outer_query: str,
	tool_calls: list[ToolCall],
	search_queries_by_call: dict[str, str],
	progress_callback: AgenticWebSearchProgressCallback | None,
) -> None:
	"""emit progress when the native agent starts an inner web_search call."""
	for tool_call in tool_calls:
		if tool_call.name != "web_search" or tool_call.id in search_queries_by_call:
			continue
		query = _query_from_tool_arguments(tool_call.arguments)
		if query is None:
			continue
		search_queries_by_call[tool_call.id] = query
		await _emit_progress(
			progress_callback,
			f"searched {_format_progress_query(query)}",
			build_agentic_web_search_progress(
				stage="search_started",
				message=f"searched {_format_progress_query(query)}",
				query=outer_query,
				agent="native",
				engine=settings.web_search.search_engines.engine,
				search_query=query,
				inner_tool_call_id=tool_call.id,
			),
		)


async def _emit_tool_result_progress(
	outer_query: str,
	message: ToolMessage,
	search_queries_by_call: dict[str, str],
	progress_callback: AgenticWebSearchProgressCallback | None,
) -> None:
	"""emit progress for a completed inner web_search result."""
	payload = _web_search_output_payload(message.tool_output)
	if payload is None:
		return
	result_items = _web_search_output_source_items(payload)
	if result_items is None:
		return
	query = search_queries_by_call.get(message.tool_call_id)
	result_count = len(result_items)
	sources: list[WebSearchSource] = []
	for item in result_items:
		source = _source_from_payload(item)
		if source is not None:
			sources.append(source)
	engine = _engine_from_tool_metadata(message)
	if query is not None:
		await _emit_progress(
			progress_callback,
			f"{_format_progress_query(query)} found {result_count} results",
			build_agentic_web_search_progress(
				stage="search_results",
				message=f"{_format_progress_query(query)} found {result_count} results",
				query=outer_query,
				agent="native",
				engine=engine,
				search_query=query,
				inner_tool_call_id=message.tool_call_id,
				result_count=result_count,
				sources=sources,
			),
		)
	else:
		await _emit_progress(
			progress_callback,
			f"found {result_count} results",
			build_agentic_web_search_progress(
				stage="search_results",
				message=f"found {result_count} results",
				query=outer_query,
				agent="native",
				engine=engine,
				inner_tool_call_id=message.tool_call_id,
				result_count=result_count,
				sources=sources,
			),
		)
	await _emit_progress(
		progress_callback,
		f"reading {result_count} results",
		build_agentic_web_search_progress(
			stage="reading_results",
			message=f"reading {result_count} results",
			query=outer_query,
			agent="native",
			engine=engine,
			search_query=query,
			inner_tool_call_id=message.tool_call_id,
			result_count=result_count,
			sources=sources,
		),
	)


async def _emit_progress(
	progress_callback: AgenticWebSearchProgressCallback | None,
	message: str,
	payload: JSONObject,
) -> None:
	"""call the optional progress callback with a frontend event payload."""
	if progress_callback is None:
		return
	await progress_callback(message, payload)


def _query_from_tool_arguments(arguments: object) -> str | None:
	"""parse a web_search query out of streamed tool-call arguments."""
	if isinstance(arguments, str):
		if not arguments.strip():
			return None
		try:
			arguments = json.loads(arguments)
		except json.JSONDecodeError:
			return None
	if not isinstance(arguments, dict):
		return None
	query = arguments.get("query")
	if isinstance(query, str) and query.strip():
		return query.strip()
	return None


def _web_search_output_payload(tool_output: str) -> JSONObject | None:
	"""parse a tool output string as a JSON object."""
	try:
		payload = json.loads(tool_output)
	except json.JSONDecodeError:
		return None
	if not isinstance(payload, dict):
		return None
	return {str(key): value for key, value in payload.items()}


def _web_search_output_source_items(payload: JSONObject) -> list[object] | None:
	"""return result resources from web_search output JSON."""
	results = payload.get("results")
	if isinstance(results, list):
		return list(results)
	return None


def _engine_from_tool_metadata(message: ToolMessage) -> SearchEngine | None:
	"""read the private search engine value attached by the web_search tool."""
	metadata = message.metadata or {}
	web_search = metadata.get("_web_search")
	if not isinstance(web_search, dict):
		return None
	match web_search.get("engine"):
		case "perplexity":
			return "perplexity"
		case "searxng":
			return "searxng"
		case "bing":
			return "bing"
		case "google":
			return "google"
		case _:
			return None


def _format_progress_query(query: str) -> str:
	"""format an inner search query for compact progress messages."""
	query = query.strip()
	if len(query) > 120:
		query = f"{query[:117]}..."
	return f'"{query}"'


def _last_assistant_text(messages: list[AssistantMessage | ToolMessage]) -> str:
	"""return the last non-empty assistant message text in native search output."""
	for message in reversed(messages):
		if isinstance(message, AssistantMessage) and message.text.strip():
			return message.text.strip()
	return ""


def _collect_engine(
	messages: list[AssistantMessage | ToolMessage],
) -> SearchEngine | None:
	"""collect the latest private search engine metadata from tool messages."""
	for message in reversed(messages):
		if not isinstance(message, ToolMessage):
			continue
		engine = _engine_from_tool_metadata(message)
		if engine is not None:
			return engine
	return None


def _collect_web_search_sources(
	messages: list[AssistantMessage | ToolMessage],
) -> list[WebSearchSource]:
	"""collect and deduplicate source results from structured tool outputs."""
	sources: list[WebSearchSource] = []
	seen_urls: set[str] = set()
	for message in messages:
		if not isinstance(message, ToolMessage):
			continue
		payload = _web_search_output_payload(message.tool_output)
		if payload is None:
			continue
		items = _web_search_output_source_items(payload)
		if items is None:
			continue
		for item in items:
			source = _source_from_payload(item)
			if source is None or source.url in seen_urls:
				continue
			seen_urls.add(source.url)
			sources.append(source)
	return sources


def _source_from_payload(value: object) -> WebSearchSource | None:
	"""normalize a source object from a JSON tool output payload."""
	if not isinstance(value, dict):
		return None
	title = value.get("title")
	url = value.get("url")
	snippet = value.get("snippet")
	if not isinstance(title, str) or not isinstance(url, str):
		return None
	if not isinstance(snippet, str):
		snippet = ""
	date = value.get("date")
	if not isinstance(date, str):
		date = None
	last_updated = value.get("last_updated")
	if not isinstance(last_updated, str):
		last_updated = None
	return WebSearchSource(
		title=title,
		url=url,
		snippet=snippet,
		date=date,
		last_updated=last_updated,
	)
