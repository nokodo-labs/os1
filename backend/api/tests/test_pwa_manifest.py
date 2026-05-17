"""Tests for PWA manifest compilation."""

from __future__ import annotations

import json

import pytest

from api.service import pwa_manifest
from api.settings.settings import BrandingSettings


def test_manifest_defaults_use_nokodo_assets_and_frontend_shortcuts(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	branding = BrandingSettings.model_validate(
		{
			"site_name": "nokodo",
			"primary_color": "#000000",
			"public_frontend_origin": "https://nokodo.dev",
			"public_cdn_origin": "https://cdn.example.com",
		}
	)
	monkeypatch.setattr(pwa_manifest.settings, "branding", branding)
	pwa_manifest.invalidate_cache()

	try:
		body, _etag = pwa_manifest.get_manifest_response()
		manifest = json.loads(body)

		assert manifest["id"] == "/"
		assert manifest["start_url"] == "https://nokodo.dev/"
		assert manifest["scope"] == "https://nokodo.dev/"
		assert manifest["display_override"] == [
			"window-controls-overlay",
			"standalone",
		]
		assert manifest["protocol_handlers"] == [
			{
				"protocol": "web+nokodo",
				"url": "https://nokodo.dev/?protocol=%s",
			},
		]
		assert manifest["icons"] == [
			{
				"src": "https://nokodo.net/static/os1/icon-1024-maskable.png",
				"type": "image/png",
				"purpose": "maskable",
				"sizes": "1024x1024",
			},
			{
				"src": "https://nokodo.net/static/os1/icon-512-any.png",
				"type": "image/png",
				"purpose": "any",
				"sizes": "512x512",
			},
		]
		assert manifest["screenshots"][0]["src"] == (
			"https://nokodo.net/static/os1/screenshots/narrow-1-1770x3835.png"
		)
		assert manifest["screenshots"][-1]["src"] == (
			"https://nokodo.net/static/os1/screenshots/wide-8-3840x2160.png"
		)
		assert [shortcut["url"] for shortcut in manifest["shortcuts"]] == [
			"https://nokodo.dev/notes",
			"https://nokodo.dev/reminders",
			"https://nokodo.dev/calendar",
			"https://nokodo.dev/messages",
			"https://nokodo.dev/projects",
			"https://nokodo.dev/library",
			"https://nokodo.dev/social",
			"https://nokodo.dev/settings",
		]
		assert manifest["shortcuts"][0]["icons"] == [
			{
				"src": "https://nokodo.dev/shortcuts/notes.png",
				"sizes": "192x192",
				"type": "image/png",
			}
		]
	finally:
		pwa_manifest.invalidate_cache()


def test_manifest_falls_back_to_request_host_default_frontend_port(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	branding = BrandingSettings.model_validate(
		{
			"site_name": "nokodo",
			"primary_color": "#000000",
		}
	)
	monkeypatch.setattr(pwa_manifest.settings, "branding", branding)
	pwa_manifest.invalidate_cache()

	try:
		body, _etag = pwa_manifest.get_manifest_response("http://localhost:1383")
		manifest = json.loads(body)

		assert manifest["start_url"] == "http://localhost:888/"
		assert manifest["scope"] == "http://localhost:888/"
		assert manifest["shortcuts"][0]["url"] == "http://localhost:888/notes"
		assert manifest["shortcuts"][0]["icons"][0]["src"] == (
			"http://localhost:888/shortcuts/notes.png"
		)
	finally:
		pwa_manifest.invalidate_cache()


def test_manifest_asset_sources_can_use_cdn_custom_and_disabled(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	branding = BrandingSettings.model_validate(
		{
			"site_name": "nokodo",
			"primary_color": "#000000",
			"public_frontend_origin": "https://app.example.com",
			"public_cdn_origin": "https://cdn.example.com",
			"pwa_assets": {
				"icon_1024_maskable": {"source": "cdn"},
				"icon_512_any": {"source": "disabled"},
				"shortcut_notes": {"source": "cdn"},
				"shortcut_reminders": {
					"source": "custom",
					"url": "https://assets.example.com/reminders.png",
				},
				"shortcut_calendar": {"source": "disabled"},
				"screenshot_narrow_1": {"source": "cdn"},
				"screenshot_narrow_2": {
					"source": "custom",
					"url": "https://assets.example.com/narrow-2.webp",
				},
				"screenshot_narrow_3": {"source": "disabled"},
			},
		}
	)
	monkeypatch.setattr(pwa_manifest.settings, "branding", branding)
	pwa_manifest.invalidate_cache()

	try:
		body, _etag = pwa_manifest.get_manifest_response()
		manifest = json.loads(body)

		assert [icon["src"] for icon in manifest["icons"]] == [
			"https://cdn.example.com/static/os1/icon-1024-maskable.png",
		]
		assert manifest["shortcuts"][0]["icons"] == [
			{
				"src": "https://cdn.example.com/static/os1/shortcuts/notes.png",
				"sizes": "192x192",
				"type": "image/png",
			}
		]
		assert manifest["shortcuts"][1]["icons"] == [
			{
				"src": "https://assets.example.com/reminders.png",
				"sizes": "192x192",
				"type": "image/png",
			}
		]
		assert manifest["shortcuts"][2]["url"] == "https://app.example.com/calendar"
		assert "icons" not in manifest["shortcuts"][2]

		screenshot_sources = [shot["src"] for shot in manifest["screenshots"]]
		assert (
			"https://cdn.example.com/static/os1/screenshots/narrow-1-1770x3835.png"
			in screenshot_sources
		)
		assert "https://assets.example.com/narrow-2.webp" in screenshot_sources
		assert (
			"https://nokodo.net/static/os1/screenshots/narrow-3-1770x3835.png"
			not in screenshot_sources
		)
	finally:
		pwa_manifest.invalidate_cache()
