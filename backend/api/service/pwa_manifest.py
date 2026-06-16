"""PWA manifest compilation and caching.

compiles a W3C web app manifest from branding and CDN settings.
the result is JSON-serialized, cached in memory, and served with an ETag.
cache is invalidated when settings change (see invalidate_cache).

- asset sources -

each generated manifest asset has its own source setting:
default, cdn, custom, or disabled. default uses nokodo-hosted app assets
except shortcut icons, which use frontend-served PNGs. cdn uses the same
well-known paths under branding.public_cdn_origin. custom uses the
per-asset URL field. disabled omits only that asset reference.

well-known CDN paths are resolved from:

{cdn}/static/os1/
+-- icon-1024-maskable.png       1024x1024 maskable app icon
+-- icon-512-any.png              512x512 any-purpose app icon
+-- shortcuts/{app}.png           192x192 transparent shortcut icons
+-- screenshots/narrow-{1..5}-1770x3835.png   mobile screenshots
+-- screenshots/wide-{1..8}-3840x2160.png     desktop screenshots
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypedDict

from api.service.web_assets import (
	STATIC_ASSET_PATH,
	cdn_asset_url,
	default_asset_url,
	resolve_asset_source,
)
from api.settings import settings
from api.settings.settings import (
	ManifestAssetSettings,
	PwaManifestAssetsSettings,
)


# -- cache state --


class ManifestCacheEntry(TypedDict):
	body: bytes
	etag: str


_cache: ManifestCacheEntry | None = None


def invalidate_cache() -> None:
	"""clear cached manifest so the next request recompiles."""
	global _cache
	_cache = None


# -- public API --


def get_manifest_response(request_origin: str | None = None) -> tuple[bytes, str]:
	"""return (body_bytes, etag) for the current manifest."""
	global _cache
	if _cache is None:
		manifest = _compile()
		body = json.dumps(manifest, separators=(",", ":")).encode()
		etag = hashlib.sha256(body).hexdigest()[:16]
		_cache = {"body": body, "etag": etag}
	return _cache["body"], _cache["etag"]


# -- internals --


class IconSpec(TypedDict):
	file: str
	sizes: str | None
	purpose: str


_ICONS: list[IconSpec] = [
	{"file": "icon-1024-maskable.png", "sizes": "1024x1024", "purpose": "maskable"},
	{"file": "icon-512-any.png", "sizes": "512x512", "purpose": "any"},
]

_SHORTCUTS = [
	{
		"name": "notes",
		"short_name": "notes",
		"description": "your notes",
		"url": "/notes",
		"icon_file": "/shortcuts/notes.png",
	},
	{
		"name": "reminders",
		"short_name": "reminders",
		"description": "your reminders",
		"url": "/reminders",
		"icon_file": "/shortcuts/reminders.png",
	},
	{
		"name": "calendar",
		"short_name": "calendar",
		"description": "your calendar",
		"url": "/calendar",
		"icon_file": "/shortcuts/calendar.png",
	},
	{
		"name": "messages",
		"short_name": "messages",
		"description": "your messages",
		"url": "/messages",
		"icon_file": "/shortcuts/messages.png",
	},
	{
		"name": "projects",
		"short_name": "projects",
		"description": "your projects",
		"url": "/projects",
		"icon_file": "/shortcuts/projects.png",
	},
	{
		"name": "files",
		"short_name": "files",
		"description": "your files",
		"url": "/library",
		"icon_file": "/shortcuts/library.png",
	},
	{
		"name": "social",
		"short_name": "social",
		"description": "friends and groups",
		"url": "/social",
		"icon_file": "/shortcuts/social.png",
	},
	{
		"name": "settings",
		"short_name": "settings",
		"description": "your settings",
		"url": "/settings",
		"icon_file": "/shortcuts/settings.png",
	},
]

_NARROW_SCREENSHOTS = 5
_NARROW_SIZE = "1770x3835"
_WIDE_SCREENSHOTS = 8
_WIDE_SIZE = "3840x2160"


def _guess_mime(filename: str) -> str:
	lower = filename.lower()
	if lower.endswith(".svg"):
		return "image/svg+xml"
	if lower.endswith(".png"):
		return "image/png"
	if lower.endswith(".webp"):
		return "image/webp"
	if lower.endswith(".jpg") or lower.endswith(".jpeg"):
		return "image/jpeg"
	if lower.endswith(".ico"):
		return "image/x-icon"
	return "image/png"


def _resolve_manifest_asset(
	asset: ManifestAssetSettings,
	default_url: str,
	cdn_url: str | None,
) -> str | None:
	return resolve_asset_source(asset.source, asset.url, default_url, cdn_url)


def _build_icons(
	cdn: str | None,
	assets: PwaManifestAssetsSettings,
) -> list[dict[str, str]]:
	icons: list[dict[str, str]] = []
	icon_specs = [
		(_ICONS[0], assets.icon_1024_maskable),
		(_ICONS[1], assets.icon_512_any),
	]
	for spec, asset in icon_specs:
		src = _resolve_manifest_asset(
			asset,
			default_asset_url(STATIC_ASSET_PATH, spec["file"]),
			cdn_asset_url(cdn, STATIC_ASSET_PATH, spec["file"]) if cdn else None,
		)
		if not src:
			continue
		entry: dict[str, str] = {
			"src": src,
			"type": _guess_mime(src),
			"purpose": spec["purpose"],
		}
		if spec["sizes"]:
			entry["sizes"] = spec["sizes"]
		icons.append(entry)
	return icons


def _build_shortcuts(
	cdn: str | None,
	assets: PwaManifestAssetsSettings,
) -> list[dict[str, Any]]:
	shortcuts: list[dict[str, Any]] = []
	shortcut_specs = [
		(_SHORTCUTS[0], assets.shortcut_notes, "notes.png"),
		(_SHORTCUTS[1], assets.shortcut_reminders, "reminders.png"),
		(_SHORTCUTS[2], assets.shortcut_calendar, "calendar.png"),
		(_SHORTCUTS[3], assets.shortcut_messages, "messages.png"),
		(_SHORTCUTS[4], assets.shortcut_projects, "projects.png"),
		(_SHORTCUTS[5], assets.shortcut_library, "library.png"),
		(_SHORTCUTS[6], assets.shortcut_social, "social.png"),
		(_SHORTCUTS[7], assets.shortcut_settings, "settings.png"),
	]
	for spec, asset, file in shortcut_specs:
		icon_src = _resolve_manifest_asset(
			asset,
			spec["icon_file"],
			cdn_asset_url(cdn, STATIC_ASSET_PATH, "shortcuts", file) if cdn else None,
		)
		entry: dict[str, Any] = {
			"name": spec["name"],
			"short_name": spec["short_name"],
			"description": spec["description"],
			"url": spec["url"],
		}
		if icon_src:
			entry["icons"] = [
				{
					"src": icon_src,
					"sizes": "192x192",
					"type": _guess_mime(icon_src),
				}
			]
		shortcuts.append(entry)
	return shortcuts


def _build_screenshots(
	cdn: str | None,
	assets: PwaManifestAssetsSettings,
) -> list[dict[str, str]]:
	shots: list[dict[str, str]] = []
	narrow_assets = [
		assets.screenshot_narrow_1,
		assets.screenshot_narrow_2,
		assets.screenshot_narrow_3,
		assets.screenshot_narrow_4,
		assets.screenshot_narrow_5,
	]
	wide_assets = [
		assets.screenshot_wide_1,
		assets.screenshot_wide_2,
		assets.screenshot_wide_3,
		assets.screenshot_wide_4,
		assets.screenshot_wide_5,
		assets.screenshot_wide_6,
		assets.screenshot_wide_7,
		assets.screenshot_wide_8,
	]
	for i, asset in enumerate(narrow_assets, start=1):
		file = f"narrow-{i}-{_NARROW_SIZE}.png"
		src = _resolve_manifest_asset(
			asset,
			default_asset_url(STATIC_ASSET_PATH, "screenshots", file),
			cdn_asset_url(cdn, STATIC_ASSET_PATH, "screenshots", file) if cdn else None,
		)
		if not src:
			continue
		shots.append(
			{
				"src": src,
				"sizes": _NARROW_SIZE,
				"type": _guess_mime(src),
				"form_factor": "narrow",
				"label": f"Narrow screenshot {i}",
			}
		)
	for i, asset in enumerate(wide_assets, start=1):
		file = f"wide-{i}-{_WIDE_SIZE}.png"
		src = _resolve_manifest_asset(
			asset,
			default_asset_url(STATIC_ASSET_PATH, "screenshots", file),
			cdn_asset_url(cdn, STATIC_ASSET_PATH, "screenshots", file) if cdn else None,
		)
		if not src:
			continue
		shots.append(
			{
				"src": src,
				"sizes": _WIDE_SIZE,
				"type": _guess_mime(src),
				"form_factor": "wide",
				"label": f"Wide screenshot {i}",
			}
		)
	return shots


def _compile() -> dict[str, Any]:
	"""build a complete PWA manifest from current settings."""
	branding = settings.branding
	cdn = (
		str(branding.public_cdn_origin).rstrip("/")
		if branding.public_cdn_origin
		else None
	)
	pwa_assets = branding.pwa_assets

	manifest: dict[str, Any] = {
		"id": "/",
		"name": branding.site_name,
		"short_name": branding.site_name,
		"description": "your interface with AI",
		"orientation": "natural",
		"start_url": "/",
		"scope": "/",
		"display_override": ["window-controls-overlay", "standalone"],
		"display": "standalone",
		"theme_color": branding.primary_color,
		"background_color": "#000000",
		"categories": [
			"education",
			"lifestyle",
			"productivity",
			"utilities",
		],
		"protocol_handlers": [
			{
				"protocol": "web+nokodo",
				"url": "/?protocol=%s",
			},
		],
	}

	icons = _build_icons(cdn, pwa_assets)
	if icons:
		manifest["icons"] = icons
	screenshots = _build_screenshots(cdn, pwa_assets)
	if screenshots:
		manifest["screenshots"] = screenshots
	manifest["shortcuts"] = _build_shortcuts(cdn, pwa_assets)

	return manifest
