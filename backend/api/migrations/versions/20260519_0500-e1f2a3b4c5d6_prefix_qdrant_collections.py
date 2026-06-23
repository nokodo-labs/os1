"""prefix qdrant collections

Revision ID: e1f2a3b4c5d6
Revises: d6b7faed3314
Create Date: 2026-05-19 05:12:21.197886

"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "d6b7faed3314"
branch_labels = None
depends_on = None


OLD_COLLECTION_TEMPLATE = "{model}_bm25"
NEW_COLLECTION_TEMPLATE = "nokodo-ai__{model}_bm25"
COLLECTION_NAMESPACE = "nokodo-ai__"
DEFAULT_QDRANT_URL = "qdrant:6334"
REQUIRED_PAYLOAD_FIELDS = frozenset(
	{
		"resource_type",
		"resource_id",
		"owner_id",
		"allowed_user_ids",
		"allowed_group_ids",
		"allowed_role_ids",
	}
)


type JsonObject = dict[str, object]


def upgrade() -> None:
	_update_collection_template_override(
		OLD_COLLECTION_TEMPLATE,
		NEW_COLLECTION_TEMPLATE,
	)
	_rename_qdrant_collections()


def downgrade() -> None:
	pass


def _update_collection_template_override(
	current_template: str,
	next_template: str,
) -> None:
	op.execute(
		sa.text(
			"""
			UPDATE settings_documents
			SET data = jsonb_set(
				data,
				'{vector,collection_template}',
				to_jsonb(CAST(:next_template AS text)),
				true
			),
			version = version + 1
			WHERE namespace = 'assets'
			AND data #>> '{vector,collection_template}' = :current_template
			"""
		).bindparams(
			sa.bindparam("current_template", current_template),
			sa.bindparam("next_template", next_template),
		)
	)


def _rename_qdrant_collections() -> None:
	config = _resolve_qdrant_config()
	if config is None:
		return
	base_url, api_key = config
	for collection_name in _list_collection_names(base_url, api_key):
		target_name = _target_collection_name(collection_name)
		if target_name is None:
			continue
		collection_info = _collection_info(base_url, api_key, collection_name)
		if not _is_nokodo_collection(collection_info):
			continue
		_copy_collection(
			base_url, api_key, collection_name, target_name, collection_info
		)


def _resolve_qdrant_config() -> tuple[str, str | None] | None:
	assets = _settings_doc("assets")
	vector_database = _nested_mapping(assets, "vector_database")
	provider = _string_value(
		os.getenv("NOKODO__ASSETS__VECTOR_DATABASE__PROVIDER"),
		_string_value(vector_database.get("provider"), "qdrant"),
	)
	if provider != "qdrant":
		return None

	qdrant = _nested_mapping(vector_database, "qdrant")
	url = _string_value(
		os.getenv("NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__URL"),
		_string_value(qdrant.get("url"), DEFAULT_QDRANT_URL),
	)
	use_grpc = _bool_value(
		os.getenv("NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__USE_GRPC"),
		_bool_value(qdrant.get("use_grpc"), True),
	)
	api_key = _optional_string_value(
		os.getenv("NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__API_KEY"),
		_optional_string_value(qdrant.get("api_key"), None),
	)
	return _qdrant_http_base_url(url, use_grpc), api_key


def _settings_doc(section: str) -> JsonObject:
	row = (
		op.get_bind()
		.execute(
			sa.text("SELECT data FROM settings_documents WHERE namespace = :section"),
			{"section": section},
		)
		.scalar()
	)
	return _mapping(row)


def _nested_mapping(
	value: Mapping[str, object],
	key: str,
) -> JsonObject:
	next_value = value.get(key)
	return _mapping(next_value)


def _string_value(value: object, fallback: str) -> str:
	return value if isinstance(value, str) and value else fallback


def _optional_string_value(value: object, fallback: str | None) -> str | None:
	if isinstance(value, str) and value:
		return value
	return fallback if fallback else None


def _bool_value(value: object, fallback: bool) -> bool:
	if isinstance(value, str) and value:
		return value.strip().lower() in {"1", "true", "yes", "on"}
	return value if isinstance(value, bool) else fallback


def _qdrant_http_base_url(url: str, use_grpc: bool) -> str:
	parsed = urllib.parse.urlparse(url if "://" in url else f"http://{url}")
	if parsed.hostname is None:
		raise RuntimeError(f"invalid qdrant url: {url}")
	scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "http"
	port = parsed.port
	if use_grpc and port == 6334:
		port = 6333
	elif port is None:
		port = 6333
	netloc = parsed.hostname if port is None else f"{parsed.hostname}:{port}"
	return urllib.parse.urlunparse((scheme, netloc, "", "", "", "")).rstrip("/")


def _target_collection_name(name: str) -> str | None:
	if name.startswith(COLLECTION_NAMESPACE):
		return None
	if name.endswith("_bm25"):
		return f"{COLLECTION_NAMESPACE}{name}"
	return None


def _is_nokodo_collection(collection_info: Mapping[str, object]) -> bool:
	payload_schema = _mapping(collection_info.get("payload_schema"))
	return REQUIRED_PAYLOAD_FIELDS.issubset(set(payload_schema))


def _copy_collection(
	base_url: str,
	api_key: str | None,
	source_name: str,
	target_name: str,
	source_info: Mapping[str, object],
) -> None:
	collection_names = set(_list_collection_names(base_url, api_key))
	if target_name not in collection_names:
		_create_collection_like(base_url, api_key, target_name, source_info)
	_ensure_payload_indexes(base_url, api_key, target_name, source_info)
	_copy_points(base_url, api_key, source_name, target_name)
	source_count = _points_count(base_url, api_key, source_name)
	target_count = _points_count(base_url, api_key, target_name)
	if source_count != target_count:
		raise RuntimeError(
			"qdrant collection copy count mismatch: "
			f"{source_name}={source_count}, {target_name}={target_count}"
		)
	_request_json(base_url, api_key, "DELETE", _collection_path(source_name))


def _create_collection_like(
	base_url: str,
	api_key: str | None,
	name: str,
	source_info: Mapping[str, object],
) -> None:
	config = _mapping(source_info.get("config"))
	params = _mapping(config.get("params"))
	body: JsonObject = {}
	for key in (
		"vectors",
		"sparse_vectors",
		"shard_number",
		"replication_factor",
		"write_consistency_factor",
		"on_disk_payload",
	):
		value = params.get(key)
		if value is not None:
			body[key] = value
	_request_json(base_url, api_key, "PUT", _collection_path(name), body)


def _ensure_payload_indexes(
	base_url: str,
	api_key: str | None,
	target_name: str,
	source_info: Mapping[str, object],
) -> None:
	target_info = _collection_info(base_url, api_key, target_name)
	existing_fields = set(_mapping(target_info.get("payload_schema")))
	source_schema = _mapping(source_info.get("payload_schema"))
	for field_name, schema in source_schema.items():
		if field_name in existing_fields or not isinstance(field_name, str):
			continue
		field_schema = _mapping(schema).get("data_type")
		if not isinstance(field_schema, str):
			continue
		body: JsonObject = {
			"field_name": field_name,
			"field_schema": field_schema,
		}
		_request_json(
			base_url,
			api_key,
			"PUT",
			f"{_collection_path(target_name)}/index",
			body,
		)


def _copy_points(
	base_url: str,
	api_key: str | None,
	source_name: str,
	target_name: str,
) -> None:
	offset: object | None = None
	while True:
		body: JsonObject = {
			"limit": 256,
			"with_payload": True,
			"with_vector": True,
		}
		if offset is not None:
			body["offset"] = offset
		result = _result(
			_request_json(
				base_url,
				api_key,
				"POST",
				f"{_collection_path(source_name)}/points/scroll",
				body,
			)
		)
		points = result.get("points")
		if isinstance(points, list) and points:
			_request_json(
				base_url,
				api_key,
				"PUT",
				f"{_collection_path(target_name)}/points?wait=true",
				{"points": points},
			)
		offset = result.get("next_page_offset")
		if offset is None:
			return


def _list_collection_names(base_url: str, api_key: str | None) -> list[str]:
	result = _result(_request_json(base_url, api_key, "GET", "/collections"))
	collections = result.get("collections")
	if not isinstance(collections, list):
		return []
	names: list[str] = []
	for collection in collections:
		name = _mapping(collection).get("name")
		if isinstance(name, str):
			names.append(name)
	return names


def _collection_info(
	base_url: str,
	api_key: str | None,
	name: str,
) -> JsonObject:
	return _result(_request_json(base_url, api_key, "GET", _collection_path(name)))


def _points_count(base_url: str, api_key: str | None, name: str) -> int:
	value = _collection_info(base_url, api_key, name).get("points_count")
	return int(value) if isinstance(value, int) else 0


def _collection_path(name: str) -> str:
	return f"/collections/{urllib.parse.quote(name, safe='')}"


def _request_json(
	base_url: str,
	api_key: str | None,
	method: str,
	path: str,
	body: JsonObject | None = None,
) -> JsonObject:
	data = None if body is None else json.dumps(body).encode("utf-8")
	headers = {"Content-Type": "application/json"}
	if api_key:
		headers["api-key"] = api_key
	request = urllib.request.Request(
		f"{base_url}{path}",
		data=data,
		headers=headers,
		method=method,
	)
	try:
		with urllib.request.urlopen(request, timeout=30) as response:
			raw = response.read()
	except urllib.error.HTTPError as exc:
		message = exc.read().decode("utf-8", errors="replace")
		raise RuntimeError(
			f"qdrant request failed: {method} {path}: {exc.code} {message}"
		) from exc
	except urllib.error.URLError as exc:
		raise RuntimeError(f"qdrant request failed: {method} {path}: {exc}") from exc
	if not raw:
		return {}
	parsed = json.loads(raw.decode("utf-8"))
	if not isinstance(parsed, dict):
		raise RuntimeError(f"qdrant returned non-object response for {method} {path}")
	return parsed


def _result(response: Mapping[str, object]) -> JsonObject:
	result = response.get("result")
	return _mapping(result)


def _mapping(value: object) -> JsonObject:
	if not isinstance(value, Mapping):
		return {}
	return {key: item for key, item in value.items() if isinstance(key, str)}
