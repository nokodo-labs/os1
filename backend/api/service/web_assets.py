"""shared web asset URL helpers."""

from dataclasses import dataclass


STATIC_ASSET_PATH = "static/os1"
DEFAULT_ASSET_ORIGIN = "https://nokodo.net"


@dataclass(frozen=True)
class MediaAssetSpec:
	default_url: str
	cdn_path: str


def strip_trailing_slash(url: str) -> str:
	return url.rstrip("/")


def origin_url(origin: str, *parts: str) -> str:
	clean_parts = [part.strip("/") for part in parts if part.strip("/")]
	if not clean_parts:
		return strip_trailing_slash(origin)
	return f"{strip_trailing_slash(origin)}/{'/'.join(clean_parts)}"


def default_asset_url(*parts: str) -> str:
	return origin_url(DEFAULT_ASSET_ORIGIN, *parts)


def cdn_asset_url(cdn: str, *parts: str) -> str:
	return origin_url(cdn, *parts)


def app_url(frontend: str, path: str) -> str:
	if not frontend:
		return path
	return origin_url(frontend, path)


def resolve_asset_source(
	source: str,
	custom_url: object | None,
	default_url: str,
	cdn_url: str | None,
) -> str | None:
	if source == "disabled":
		return None
	if custom_url:
		return str(custom_url)
	if source == "cdn" and cdn_url:
		return cdn_url
	return default_url


MEDIA_ASSETS: dict[str, MediaAssetSpec] = {
	"favicon": MediaAssetSpec(
		default_url=default_asset_url(STATIC_ASSET_PATH, "favicon.svg"),
		cdn_path=f"{STATIC_ASSET_PATH}/favicon.svg",
	),
	"apple_touch_icon": MediaAssetSpec(
		default_url=default_asset_url(STATIC_ASSET_PATH, "icon-512-any.png"),
		cdn_path=f"{STATIC_ASSET_PATH}/icon-512-any.png",
	),
	"sidebar_logo": MediaAssetSpec(
		default_url=default_asset_url(STATIC_ASSET_PATH, "sidebar-logo.svg"),
		cdn_path=f"{STATIC_ASSET_PATH}/sidebar-logo.svg",
	),
	"splash_logo": MediaAssetSpec(
		default_url=default_asset_url(STATIC_ASSET_PATH, "splash-logo.svg"),
		cdn_path=f"{STATIC_ASSET_PATH}/splash-logo.svg",
	),
}
