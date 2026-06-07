"""tests for api.settings."""

from __future__ import annotations

import os
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import PydanticBaseSettingsSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.boot_settings import boot_settings
from api.models.setting import SettingsDocument
from api.schemas.user import UserCreate
from api.settings import (
	DEFAULT_SECRET_KEY,
	BrandingSettings,
	DbSettingsSource,
	MCPIntegrationSettings,
	QdrantVectorDatabaseSettings,
	SecuritySettings,
	Settings,
	settings,
)
from api.settings import database as settings_db
from api.settings.settings import (
	MediaAssetSettings,
	MediaSettings,
	_LenientDotEnvSettingsSource,
	_LenientEnvSettingsSource,
	get_field_flags,
	settings_field,
)
from api.v1.schemas.settings import SettingsPatch
from api.v1.service import settings as settings_svc
from api.v1.service import users as user_service


def test_settings_model_config_has_env_file() -> None:
	"""ensure Settings loads .env file - regression test for missing env_file config."""
	config = Settings.model_config
	assert config.get("env_file") == ".env", (
		"Settings.model_config must have env_file='.env' to load .env files"
	)


def test_settings_reload_updates_imported_singleton(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	settings_id = id(settings)
	previous_env = os.environ.get("NOKODO__BRANDING__SITE_NAME")

	def _boom() -> Any:
		raise RuntimeError("no db")

	monkeypatch.setattr(settings_db, "async_session_local", _boom)

	try:
		monkeypatch.setenv("NOKODO__BRANDING__SITE_NAME", "reload_test_1")
		settings.reload()
		assert id(settings) == settings_id
		assert settings.branding.site_name == "reload_test_1"

		monkeypatch.setenv("NOKODO__BRANDING__SITE_NAME", "reload_test_2")
		settings.reload()
		assert id(settings) == settings_id
		assert settings.branding.site_name == "reload_test_2"
	finally:
		if previous_env is None:
			monkeypatch.delenv("NOKODO__BRANDING__SITE_NAME", raising=False)
		else:
			monkeypatch.setenv("NOKODO__BRANDING__SITE_NAME", previous_env)
		settings.reload()


def test_settings_field_flags_and_private_dump() -> None:
	assert get_field_flags(SecuritySettings, "secret_key") == {"write_locked": True}
	assert get_field_flags(BrandingSettings, "site_name") == {"public": True}
	assert get_field_flags(BrandingSettings, "analytics_key") == {
		"write_locked": True,
	}
	assert get_field_flags(SecuritySettings, "secret_key_uses_default") == {}

	full = settings.custom_dump(exclude_private=False)
	assert "secret_key" in full["security"]
	assert "analytics_key" in full["branding"]
	assert "api_key" in full["assets"]["vector_database"]["qdrant"]
	assert "url" in full["cache"]["redis"]
	assert "web_search" in full
	assert "tasks" in full

	public = settings.custom_dump(exclude_private=True)
	assert "ui" in public
	assert "branding" in public
	assert "media" in public
	assert "assets" not in public
	assert set(public["limits"]) == {"max_chat_input_chars"}
	assert set(public["notifications"]) == {"web_push_enabled", "vapid_public_key"}
	assert "soft_delete" not in public
	assert "web_search" not in public
	assert "code_interpreter" not in public
	assert "default_permissions" not in public
	assert "integrations" not in public
	assert "cache" not in public
	assert "tasks" not in public
	assert set(public["ai"]) == {"default_agent_ids"}
	assert "secret_key" not in public["security"]
	assert "secret_key_uses_default" not in public["security"]
	assert set(public["security"]) == {"allow_signups", "oidc"}
	assert set(public["security"]["oidc"]) == {"only"}
	assert "analytics_key" not in public["branding"]
	assert str(public["media"]["favicon"]["url"]) == (
		"https://nokodo.net/static/os1/favicon.svg"
	)

	# exercise both branches of the cors_origins validator
	security_from_list = SecuritySettings.model_validate({"cors_origins": ["http://x"]})
	assert security_from_list.cors_origins == ["http://x"]

	security_from_str = SecuritySettings.model_validate(
		{"cors_origins": "http://a, http://b"}
	)
	assert security_from_str.cors_origins == ["http://a", "http://b"]


def test_get_field_flags_empty_cases() -> None:
	class NoExtra(BaseModel):
		x: int = 1

	assert get_field_flags(NoExtra, "x") == {}
	assert get_field_flags(NoExtra, "nope") == {}


def test_settings_field_helper_sets_flags() -> None:
	class M(BaseModel):
		no_flags: str = settings_field(default="x")
		public: str = settings_field(default="x", public=True)
		locked: str = settings_field(default="x", write_locked=True)
		public_locked: str = settings_field(
			default="x",
			public=True,
			write_locked=True,
		)
		with_extra: str = settings_field(
			default="x",
			json_schema_extra={"x-custom": "kept"},
			public=True,
		)

	assert M.model_fields["no_flags"].json_schema_extra is None
	assert M.model_fields["public"].json_schema_extra == {"public": True}
	assert M.model_fields["locked"].json_schema_extra == {"write_locked": True}
	assert M.model_fields["locked"].frozen is True
	assert M.model_fields["public"].frozen is False
	assert M.model_fields["public_locked"].json_schema_extra == {
		"public": True,
		"write_locked": True,
	}
	assert M.model_fields["with_extra"].json_schema_extra == {
		"x-custom": "kept",
		"public": True,
	}


def test_public_settings_visibility_is_leaf_based() -> None:
	class Child(BaseModel):
		visible: str = settings_field(default="visible", public=True)
		hidden: str = settings_field(default="hidden")

	class Root(BaseModel):
		child: Child = settings_field(default_factory=Child)
		parent_public_child: Child = settings_field(default_factory=Child, public=True)

	data = Root().model_dump(exclude=Settings._build_public_exclude(Root))

	assert data == {
		"child": {"visible": "visible"},
		"parent_public_child": {"visible": "visible"},
	}


def test_qdrant_vector_database_defaults() -> None:
	config = QdrantVectorDatabaseSettings()
	assert config.url == "qdrant:6334"
	assert config.use_grpc is True


def test_runtime_security_rejects_default_secret_in_production(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	runtime_settings = Settings(
		security=SecuritySettings(secret_key=DEFAULT_SECRET_KEY)
	)
	monkeypatch.setattr(boot_settings, "TESTING", False)
	monkeypatch.setattr(boot_settings, "ENV", "production")

	with pytest.raises(RuntimeError, match="SECRET_KEY must be changed"):
		runtime_settings.validate_runtime_security()


def test_runtime_security_allows_default_secret_outside_production(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	runtime_settings = Settings(
		security=SecuritySettings(secret_key=DEFAULT_SECRET_KEY)
	)
	monkeypatch.setattr(boot_settings, "TESTING", False)
	monkeypatch.setattr(boot_settings, "ENV", "dev")

	runtime_settings.validate_runtime_security()


def test_settings_patch_accepts_web_search_and_integration_updates() -> None:
	patch = SettingsPatch.model_validate(
		{
			"ai": {
				"tasks": {
					"web_search_model_id": "model-chat",
					"maintenance_max_chars_per_message": 3000,
				},
				"context_compaction": {
					"recovery_target_ratio": 0.55,
					"target_usage_cap_tokens": 64000,
					"summary_batch_min_tokens": 512,
					"summary_batch_max_tokens": 16000,
					"prompt_overhead_tokens": 300,
					"blocking_summarization_enabled": True,
					"blocking_summarization_timeout_seconds": 20.0,
					"summarization_max_chars_per_message": 3000,
				},
			},
			"limits": {
				"max_reminder_hierarchy_depth": 12,
				"max_scheduled_items_window_days": 730,
			},
			"web_search": {
				"agentic": {
					"agent": "native",
					"model_id": "model-chat",
					"system_prompt": "search carefully",
					"model_params": {"temperature": 0.1},
					"max_iterations": 6,
				},
				"max_chars": 60000,
				"blacklisted_domains": ["example.com"],
				"search_engines": {"engine": "perplexity"},
				"web_loaders": {"engine": "native", "max_chars": 40000},
			},
			"integrations": {
				"perplexity": {
					"api_key": "pplx-key",
					"model": "sonar",
					"search_context_usage": "high",
					"temperature": 0.1,
					"image_results_enabled": True,
					"max_concurrent_requests": 4,
				},
				"searxng": {
					"instance_url": "http://searxng.local",
					"max_results": 12,
					"max_concurrent_requests": 3,
					"timeout_seconds": 8,
				},
			},
			"code_interpreter": {
				"max_file_download_mb": 20,
				"max_output_chars": 200000,
				"truncation_lines": 25,
			},
			"cache": {
				"scheduled_items_ttl_seconds": 60,
				"resource_payload_ttl_seconds": 45,
			},
			"tasks": {
				"thread_maintenance": {
					"inactivity_hours": 6,
					"queued_supersede_after_minutes": 3,
					"active_supersede_after_minutes": 20,
					"runner_timeout_seconds": 1200,
					"stale_task_cleanup_after_minutes": 35,
				},
				"maintenance_backfill": {
					"enabled": True,
					"cron": "*/30 * * * *",
					"batch_size": 25,
					"max_lookback_days": 90,
					"min_inactivity_hours": 12,
				},
				"file_maintenance": {
					"enabled": True,
					"cron": "*/15 * * * *",
					"batch_size": 30,
				},
			},
		}
	)

	dumped = patch.model_dump(exclude_unset=True)
	assert dumped["web_search"]["agentic"]["agent"] == "native"
	assert dumped["web_search"]["web_loaders"]["max_chars"] == 40000
	assert dumped["integrations"]["perplexity"]["image_results_enabled"] is True
	assert dumped["tasks"]["thread_maintenance"]["inactivity_hours"] == 6
	assert dumped["tasks"]["thread_maintenance"]["runner_timeout_seconds"] == 1200
	assert dumped["tasks"]["maintenance_backfill"]["enabled"] is True
	assert dumped["tasks"]["maintenance_backfill"]["batch_size"] == 25
	assert dumped["tasks"]["file_maintenance"]["enabled"] is True
	assert dumped["tasks"]["file_maintenance"]["batch_size"] == 30


def test_mcp_settings_origin_policy_and_transport_validation() -> None:
	mcp = MCPIntegrationSettings.model_validate(
		{
			"allowed_transports": ["streamable_http", "sse", "sse"],
			"user_server_origin_mode": "deny",
			"user_server_origins": [
				"HTTPS://tools.example.com/",
				"https://tools.example.com",
				"",
			],
		}
	)

	assert mcp.allowed_transports == ["streamable_http", "sse"]
	assert mcp.user_server_origins == ["https://tools.example.com"]

	with pytest.raises(ValidationError):
		MCPIntegrationSettings.model_validate({"allowed_transports": []})

	with pytest.raises(ValidationError, match="MCP origin allow mode"):
		MCPIntegrationSettings.model_validate({"user_server_origin_mode": "allow"})

	with pytest.raises(ValidationError, match="MCP origin allow mode"):
		SettingsPatch.model_validate(
			{
				"integrations": {
					"mcp": {
						"user_server_origin_mode": "allow",
						"user_server_origins": [],
					}
				}
			}
		)


def test_settings_patch_rejects_old_web_search_integration_nesting() -> None:
	with pytest.raises(ValidationError):
		SettingsPatch.model_validate(
			{
				"web_search": {
					"search_agent": "native",
					"perplexity": {"api_key": "pplx-key"},
					"search_engines": {
						"engine": "perplexity",
						"searxng": {"instance_url": "http://searxng.local"},
					},
				}
			}
		)


def test_settings_patch_distinguishes_missing_and_nullable_null() -> None:
	assert SettingsPatch.model_validate({}).model_dump(exclude_unset=True) == {}
	assert SettingsPatch.model_validate(
		{"media": {"favicon": {"url": None}}}
	).model_dump(exclude_unset=True) == {"media": {"favicon": {"url": None}}}
	assert SettingsPatch.model_validate(
		{
			"branding": {
				"pwa_assets": {"screenshot_wide_8": {"source": "disabled", "url": None}}
			}
		}
	).model_dump(exclude_unset=True) == {
		"branding": {
			"pwa_assets": {"screenshot_wide_8": {"source": "disabled", "url": None}}
		}
	}

	with pytest.raises(ValidationError):
		SettingsPatch.model_validate({"ui": None})
	with pytest.raises(ValidationError):
		SettingsPatch.model_validate({"ui": {"default_theme": None}})

	schema = SettingsPatch.model_json_schema()
	assert "null" not in str(
		schema["$defs"]["UISettingsPatch"]["properties"]["default_theme"]
	)
	assert "null" in str(
		schema["$defs"]["MediaAssetSettingsPatch"]["properties"]["url"]
	)


def test_public_media_asset_urls_resolve_from_raw_settings() -> None:
	runtime_settings = Settings(
		branding=BrandingSettings.model_validate(
			{"public_cdn_origin": "https://cdn.example.com"}
		),
		media=MediaSettings(
			favicon=MediaAssetSettings(source="cdn"),
			apple_touch_icon=MediaAssetSettings.model_validate(
				{
					"source": "custom",
					"url": "https://assets.example.com/apple.png",
				}
			),
			sidebar_logo=MediaAssetSettings.model_validate(
				{
					"source": "default",
					"url": "https://assets.example.com/logo.svg",
				}
			),
		),
	)

	assert runtime_settings.media.model_dump(mode="json") == {
		"favicon": {
			"source": "cdn",
			"url": None,
		},
		"apple_touch_icon": {
			"source": "custom",
			"url": "https://assets.example.com/apple.png",
		},
		"sidebar_logo": {
			"source": "default",
			"url": "https://assets.example.com/logo.svg",
		},
		"splash_logo": {
			"source": "default",
			"url": None,
		},
	}

	public = runtime_settings.custom_dump(exclude_private=True)
	assert public["media"] == {
		"favicon": {
			"source": "cdn",
			"url": "https://cdn.example.com/static/os1/favicon.svg",
		},
		"apple_touch_icon": {
			"source": "custom",
			"url": "https://assets.example.com/apple.png",
		},
		"sidebar_logo": {
			"source": "default",
			"url": "https://assets.example.com/logo.svg",
		},
		"splash_logo": {
			"source": "default",
			"url": "https://nokodo.net/static/os1/splash-logo.svg",
		},
	}


@pytest.mark.asyncio
async def test_settings_update_persists_pwa_asset_sources(
	db_session: AsyncSession,
) -> None:
	patch = SettingsPatch.model_validate(
		{
			"branding": {
				"pwa_assets": {
					"screenshot_narrow_1": {"source": "disabled", "url": None},
					"screenshot_wide_8": {"source": "disabled", "url": None},
				}
			}
		}
	)

	await settings_svc.update(db_session, patch)
	await db_session.commit()

	result = await db_session.execute(
		select(SettingsDocument).where(SettingsDocument.namespace == "branding")
	)
	doc = result.scalar_one()
	assert doc.data["pwa_assets"]["screenshot_narrow_1"] == {
		"source": "disabled",
		"url": None,
	}
	assert doc.data["pwa_assets"]["screenshot_wide_8"] == {
		"source": "disabled",
		"url": None,
	}


@pytest.mark.asyncio
async def test_generate_vapid_keypair_endpoint_returns_keys_without_persisting(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="vapid_admin@example.com",
			username="vapid_admin",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user.email, "password": "password123"},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]

	resp = await client.post(
		"/v1/settings/vapid-keypair",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert resp.status_code == 200
	keypair = resp.json()
	assert keypair["public_key"]
	assert keypair["private_key"].startswith("-----BEGIN PRIVATE KEY-----")

	result = await db_session.execute(
		select(SettingsDocument).where(SettingsDocument.namespace == "notifications")
	)
	assert result.scalar_one_or_none() is None

	patch_resp = await client.patch(
		"/v1/settings",
		json={
			"data": {
				"notifications": {
					"vapid_public_key": keypair["public_key"],
					"vapid_private_key": keypair["private_key"],
				}
			}
		},
		headers={"Authorization": f"Bearer {token}"},
	)
	assert patch_resp.status_code == 200
	result = await db_session.execute(
		select(SettingsDocument).where(SettingsDocument.namespace == "notifications")
	)
	doc = result.scalar_one()
	assert doc.data["vapid_public_key"] == keypair["public_key"]
	assert doc.data["vapid_private_key"] == keypair["private_key"]


@pytest.mark.asyncio
async def test_settings_write_locked_fields_not_writable(
	db_session: AsyncSession,
) -> None:
	# schema doesn't include write_locked fields, but service defends in depth.
	class MaliciousPatch(SettingsPatch):
		def model_dump(
			self, exclude_unset: bool = False, **kwargs: Any
		) -> dict[str, Any]:  # type: ignore[override]
			_ = exclude_unset, kwargs
			return {
				"branding": {"app_version": "9.9.9"},
				"security": {"secret_key": "hacked"},
			}

	patch = MaliciousPatch()

	with pytest.raises(ValueError, match="not writable"):
		await settings_svc.update(db_session, patch)


def _make_test_session_local(
	db_session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
	engine = db_session.bind
	assert engine is not None
	return async_sessionmaker(
		engine,
		class_=AsyncSession,
		expire_on_commit=False,
		autocommit=False,
		autoflush=False,
	)


@pytest.mark.asyncio
async def test_db_settings_source_loads_overrides_sync_and_excludes_write_locked(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	test_session_local = _make_test_session_local(db_session)
	monkeypatch.setattr(settings_db, "async_session_local", test_session_local)
	monkeypatch.setattr(settings_db.boot_settings, "TESTING", False)

	db_session.add(
		SettingsDocument(
			namespace="branding",
			data={
				"site_name": "from_db",
				"app_version": "0.9.9",
				"analytics_key": "secret",
			},
			version=1,
		)
	)
	db_session.add(
		SettingsDocument(
			namespace="cache",
			data={
				"redis": {"url": "redis://example.invalid/0"},
			},
			version=1,
		)
	)
	db_session.add(
		SettingsDocument(
			namespace="tasks",
			data={"taskiq": {"queue_name": "wrong"}},
			version=1,
		)
	)
	db_session.add(
		SettingsDocument(
			namespace="notifications",
			data={
				"vapid_public_key": "public",
				"vapid_private_key": "private",
				"vapid_subject": "mailto:wrong@example.com",
			},
			version=1,
		)
	)
	await db_session.commit()

	overrides = settings_db._load_db_overrides(Settings)
	assert overrides == {
		"branding": {"site_name": "from_db"},
		"notifications": {
			"vapid_public_key": "public",
			"vapid_private_key": "private",
		},
	}

	source = DbSettingsSource(Settings)
	assert source.get_field_value(None, "x") == (None, "x", False)
	assert source() == overrides


@pytest.mark.asyncio
async def test_db_settings_source_loads_overrides_inside_running_loop(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	test_session_local = _make_test_session_local(db_session)
	monkeypatch.setattr(settings_db, "async_session_local", test_session_local)
	monkeypatch.setattr(settings_db.boot_settings, "TESTING", False)

	db_session.add(
		SettingsDocument(
			namespace="branding",
			data={"site_name": "from_db_async"},
			version=1,
		)
	)
	await db_session.commit()

	# calling from inside the event loop exercises the threadpool branch
	overrides = settings_db._load_db_overrides(Settings)
	assert overrides == {"branding": {"site_name": "from_db_async"}}


def test_settings_customise_sources_includes_db_source() -> None:
	class StubSource(PydanticBaseSettingsSource):
		def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
			return None, field_name, False

		def __call__(self) -> dict[str, Any]:
			return {}

	init_settings = StubSource(Settings)
	env_settings = StubSource(Settings)
	dotenv_settings = StubSource(Settings)
	file_secret_settings = StubSource(Settings)

	sources = Settings.settings_customise_sources(
		Settings,
		init_settings,
		env_settings,
		dotenv_settings,
		file_secret_settings,
	)

	assert sources[0] is init_settings
	assert isinstance(sources[1], DbSettingsSource)
	assert sources[1].settings_cls is Settings
	assert isinstance(sources[2], _LenientEnvSettingsSource)
	assert isinstance(sources[3], _LenientDotEnvSettingsSource)
	assert sources[4] is file_secret_settings


def test_db_overrides_filters_invalid_sections_and_non_models(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(settings_db.boot_settings, "TESTING", False)

	class DummySettings(Settings):
		ui: int = 1  # type: ignore[assignment]

	class Doc:
		def __init__(self, namespace: str, data: dict[str, Any] | None):
			self.namespace = namespace
			self.data = data

	docs = [
		Doc("nope", {"x": 1}),
		Doc("branding", None),
		Doc("ui", {"x": 1}),
		Doc("security", {"secret_key": "hacked"}),
		Doc("branding", {"site_name": "ok"}),
	]

	class FakeResult:
		def scalars(self) -> FakeResult:
			return self

		def all(self) -> list[Doc]:
			return docs

	class FakeSession:
		async def __aenter__(self) -> FakeSession:
			return self

		async def __aexit__(
			self,
			exc_type: type[BaseException] | None,
			exc: BaseException | None,
			tb: Any,
		) -> None:
			return None

		async def execute(self, stmt: Any) -> FakeResult:
			_ = stmt
			return FakeResult()

	def fake_session_local() -> FakeSession:
		return FakeSession()

	monkeypatch.setattr(settings_db, "async_session_local", fake_session_local)
	assert settings_db._load_db_overrides(DummySettings) == {
		"branding": {"site_name": "ok"}
	}


def test_is_write_locked_handles_missing_and_non_dict_extra() -> None:
	class WeirdExtra(BaseModel):
		x: str = Field(json_schema_extra=lambda _: None)

	assert settings_db._is_write_locked(WeirdExtra, "nope") is False
	assert settings_db._is_write_locked(WeirdExtra, "x") is False


def test_db_settings_source_returns_empty_on_error(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(settings_db.boot_settings, "TESTING", False)

	def _boom() -> Any:
		raise RuntimeError("db down")

	monkeypatch.setattr(settings_db, "async_session_local", _boom)
	assert settings_db._load_db_overrides(Settings) == {}
