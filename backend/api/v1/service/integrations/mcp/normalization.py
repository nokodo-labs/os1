"""MCP naming and schema helpers."""

from __future__ import annotations

import hashlib
import json
import re

from nokodo_ai.types.json import JSONObject, JSONValue


MAX_MCP_TOOL_NAME_LENGTH = 64
MAX_MCP_PROMPT_COMMAND_LENGTH = 120


def normalized_mcp_tool_name(server_name: str, tool_name: str) -> str:
	"""return a provider-safe function name for an MCP tool."""
	server = _safe_name_component(server_name).lower()
	tool = _safe_name_component(tool_name).lower()
	base = f"mcp_{server}_{tool}".strip("_") or "mcp_tool"
	digest = hashlib.sha1(
		f"{server_name}\0{tool_name}".encode(), usedforsecurity=False
	).hexdigest()[:10]
	suffix = f"_{digest}"
	base_limit = MAX_MCP_TOOL_NAME_LENGTH - len(suffix)
	prefix = base[:base_limit].rstrip("_") or "mcp_tool"
	return f"{prefix}{suffix}"[:MAX_MCP_TOOL_NAME_LENGTH]


def normalized_mcp_prompt_command(
	server_id: str,
	prompt_id: str,
	prompt_name: str | None = None,
) -> str:
	"""return a stable prompt command for an MCP prompt snapshot."""
	server = _safe_prompt_component(server_id).lower()
	prompt = _safe_prompt_component(prompt_id).lower()
	base = f"mcp-{server}-{prompt}".strip("-") or "mcp-prompt"
	if prompt_name:
		slug = _safe_prompt_component(prompt_name).lower()
		if slug:
			base = f"{base}-{slug}"
	return base[:MAX_MCP_PROMPT_COMMAND_LENGTH].rstrip("-") or "mcp-prompt"


def schema_hash(*values: JSONValue) -> str:
	"""hash JSON-compatible values for discovery change detection."""
	payload = json.dumps(
		values, sort_keys=True, separators=(",", ":"), ensure_ascii=False
	)
	return hashlib.sha256(payload.encode()).hexdigest()


def normalized_input_schema(schema: JSONObject | None) -> JSONObject:
	"""normalize an MCP input schema enough for tool-calling providers."""
	if not schema:
		return {"type": "object", "properties": {}}
	normalized = _rewrite_definitions(schema)
	normalized = _repair_object_schema(normalized)
	if not isinstance(normalized, dict):
		return {"type": "object", "properties": {}}
	if normalized.get("type") == "object" and "properties" not in normalized:
		return {**normalized, "properties": {}}
	return normalized


def _safe_name_component(value: str) -> str:
	return re.sub(r"[^A-Za-z0-9_]", "_", value.strip()).strip("_")


def _safe_prompt_component(value: str) -> str:
	return re.sub(r"[^A-Za-z0-9-]", "-", value.strip()).strip("-")


def _rewrite_definitions(value: JSONValue) -> JSONValue:
	if isinstance(value, dict):
		result: JSONObject = {}
		for key, item in value.items():
			out_key = "$defs" if key == "definitions" else key
			result[out_key] = _rewrite_definitions(item)
		ref = result.get("$ref")
		if isinstance(ref, str) and ref.startswith("#/definitions/"):
			result["$ref"] = "#/$defs/" + ref[len("#/definitions/") :]
		return result
	if isinstance(value, list):
		return [_rewrite_definitions(item) for item in value]
	return value


def _repair_object_schema(value: JSONValue) -> JSONValue:
	if isinstance(value, list):
		return [_repair_object_schema(item) for item in value]
	if not isinstance(value, dict):
		return value

	repaired: JSONObject = {
		key: _repair_object_schema(item) for key, item in value.items()
	}
	if not repaired.get("type") and (
		"properties" in repaired or "required" in repaired
	):
		repaired["type"] = "object"
	if repaired.get("type") == "object":
		properties = repaired.get("properties")
		if not isinstance(properties, dict):
			repaired["properties"] = {}
		properties = repaired.get("properties")
		required = repaired.get("required")
		if isinstance(required, list) and isinstance(properties, dict):
			valid: list[JSONValue] = [
				item
				for item in required
				if isinstance(item, str) and item in properties
			]
			if valid:
				repaired["required"] = valid
			else:
				repaired.pop("required", None)
	return repaired
