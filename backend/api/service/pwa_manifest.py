"""PWA manifest compilation and caching.

compiles a W3C web app manifest from branding, media, and CDN settings.
the result is JSON-serialized, cached in memory, and served with an ETag.
cache is invalidated when settings change (see invalidate_cache).

- CDN asset paths -

when branding.public_cdn_origin is set, the manifest includes icons,
shortcuts, and screenshots resolved from well-known CDN paths:

  {cdn}/static/os1/
  +-- icon-1024-maskable.png       1024x1024 maskable app icon
  +-- icon-512-maskable.png         512x512 maskable app icon
  +-- favicon.svg                   SVG favicon (any maskable)
  +-- shortcuts/
  |   +-- notes-1024.png            shortcut icon: notes
  |   +-- reminders-1024.png        shortcut icon: reminders
  |   +-- projects-1024.png         shortcut icon: projects
  |   +-- library-1024.png          shortcut icon: library
  |   +-- social-1024.png           shortcut icon: social
  +-- screenshots/
      +-- narrow-{1..5}-1770x3835.png   mobile screenshots
      +-- wide-{1..8}-3840x2160.png     desktop screenshots

operators must host these files at the CDN origin for PWA install
prompts to show icons and screenshots. missing files are harmless
(browsers skip broken icon/screenshot URLs gracefully).

when public_cdn_origin is NOT set, the manifest still includes the
basic metadata (name, colors, display mode) but omits all asset
references that would produce broken URLs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypedDict

from api.settings import settings


# -- cache state --

_cache: dict[str, Any] = {"bytes": None, "etag": None}


def invalidate_cache() -> None:
	"""clear cached manifest so the next request recompiles."""
	_cache["bytes"] = None
	_cache["etag"] = None


# -- public API --


def get_manifest_response() -> tuple[bytes, str]:
	"""return (body_bytes, etag) for the current manifest."""
	if _cache["bytes"] is None:
		manifest = _compile()
		body = json.dumps(manifest, separators=(",", ":")).encode()
		etag = hashlib.sha256(body).hexdigest()[:16]
		_cache["bytes"] = body
		_cache["etag"] = etag
	return _cache["bytes"], _cache["etag"]


# -- internals --

# well-known CDN paths relative to {cdn}/static/os1
_STATIC = "static/os1"

class IconSpec(TypedDict):
	file: str
	sizes: str | None
	purpose: str


_ICONS: list[IconSpec] = [
	{"file": "icon-1024-maskable.png", "sizes": "1024x1024", "purpose": "maskable"},
	{"file": "icon-512-maskable.png", "sizes": "512x512", "purpose": "maskable"},
	{"file": "favicon.svg", "sizes": None, "purpose": "any maskable"},
]

_SHORTCUTS = [
	{
		"name": "notes",
		"short_name": "notes",
		"description": "your notes",
		"url": "/notes",
		"icon_file": "shortcuts/notes-1024.png",
	},
	{
		"name": "reminders",
		"short_name": "reminders",
		"description": "your reminders",
		"url": "/reminders",
		"icon_file": "shortcuts/reminders-1024.png",
	},
	{
		"name": "projects",
		"short_name": "projects",
		"description": "your projects",
		"url": "/projects",
		"icon_file": "shortcuts/projects-1024.png",
	},
	{
		"name": "library",
		"short_name": "library",
		"description": "your files",
		"url": "/library",
		"icon_file": "shortcuts/library-1024.png",
	},
	{
		"name": "social",
		"short_name": "social",
		"description": "friends and groups",
		"url": "/social",
		"icon_file": "shortcuts/social-1024.png",
	},
]

_NARROW_SCREENSHOTS = 5
_NARROW_SIZE = "1770x3835"
_WIDE_SCREENSHOTS = 8
_WIDE_SIZE = "3840x2160"


def _cdn_url(cdn: str, *parts: str) -> str:
	return f"{cdn}/{'/'.join(parts)}"


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


def _build_icons(cdn: str) -> list[dict[str, str]]:
	icons: list[dict[str, str]] = []
	for spec in _ICONS:
		entry: dict[str, str] = {
			"src": _cdn_url(cdn, _STATIC, spec["file"]),
			"type": _guess_mime(spec["file"]),
			"purpose": spec["purpose"],
		}
		if spec["sizes"]:
			entry["sizes"] = spec["sizes"]
		icons.append(entry)
	return icons


def _build_shortcuts(cdn: str) -> list[dict[str, Any]]:
	shortcuts: list[dict[str, Any]] = []
	for spec in _SHORTCUTS:
		shortcuts.append(
			{
				"name": spec["name"],
				"short_name": spec["short_name"],
				"description": spec["description"],
				"url": spec["url"],
				"icons": [
					{
						"src": _cdn_url(cdn, _STATIC, spec["icon_file"]),
						"sizes": "1024x1024",
						"type": "image/png",
					}
				],
			}
		)
	return shortcuts


def _build_screenshots(cdn: str) -> list[dict[str, str]]:
	shots: list[dict[str, str]] = []
	base = f"{cdn}/{_STATIC}/screenshots"
	for i in range(1, _NARROW_SCREENSHOTS + 1):
		shots.append(
			{
				"src": f"{base}/narrow-{i}-{_NARROW_SIZE}.png",
				"sizes": _NARROW_SIZE,
				"type": "image/png",
				"form_factor": "narrow",
				"label": f"Narrow screenshot {i}",
			}
		)
	for i in range(1, _WIDE_SCREENSHOTS + 1):
		shots.append(
			{
				"src": f"{base}/wide-{i}-{_WIDE_SIZE}.png",
				"sizes": _WIDE_SIZE,
				"type": "image/png",
				"form_factor": "wide",
				"label": f"Wide screenshot {i}",
			}
		)
	return shots


def _compile() -> dict[str, Any]:
	"""build a complete PWA manifest from current settings."""
	branding = settings.branding
	frontend = (
		str(branding.public_frontend_origin).rstrip("/")
		if branding.public_frontend_origin
		else ""
	)
	cdn = (
		str(branding.public_cdn_origin).rstrip("/")
		if branding.public_cdn_origin
		else None
	)

	manifest: dict[str, Any] = {
		"name": branding.site_name,
		"short_name": branding.site_name,
		"description": "your interface with AI",
		"orientation": "natural",
		"start_url": f"{frontend}/",
		"scope": f"{frontend}/",
		"display": "standalone",
		"theme_color": branding.primary_color,
		"background_color": "#000000",
		"categories": [
			"education",
			"lifestyle",
			"productivity",
			"utilities",
		],
	}

	if cdn:
		manifest["icons"] = _build_icons(cdn)
		manifest["shortcuts"] = _build_shortcuts(cdn)
		manifest["screenshots"] = _build_screenshots(cdn)

	return manifest
