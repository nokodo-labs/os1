/**
 * media asset URL resolution.
 *
 * resolves asset URLs from settings with a two-tier cascade:
 *   1. individual url field (e.g. settings.media.favicon_url)
 *   2. base_url + well-known filename (e.g. {base_url}/favicon.ico)
 *   → null when nothing is configured (no tag rendered)
 *
 * well-known filenames (appended to base_url):
 *   favicon.ico, apple-touch-icon.png, sidebar-logo.svg, splash-logo.svg
 */

import { settingsState } from '$lib/stores/settings.svelte'

/** well-known asset filenames appended to media.base_url. */
const WELL_KNOWN: Record<string, string> = {
	favicon: 'favicon.ico',
	appleTouchIcon: 'apple-touch-icon.png',
	sidebarLogo: 'sidebar-logo.svg',
	splashLogo: 'splash-logo.svg',
}

function stripTrailingSlash(url: string): string {
	return url.endsWith('/') ? url.slice(0, -1) : url
}

/** resolve a media asset URL. returns null when unconfigured. */
function resolve(
	key: string,
	override: string | null | undefined,
	baseUrl: string | null | undefined
): string | null {
	if (override) return override
	if (baseUrl && WELL_KNOWN[key]) {
		return `${stripTrailingSlash(baseUrl)}/${WELL_KNOWN[key]}`
	}
	return null
}

/** resolved media URLs - reactive derivation from settings. */
export function getMediaUrls(): {
	favicon: string | null
	appleTouchIcon: string | null
	manifest: string | null
	sidebarLogo: string | null
	splashLogo: string | null
} {
	const media = settingsState.data?.media
	const baseUrl = media?.base_url ?? null

	return {
		favicon: resolve('favicon', media?.favicon_url, baseUrl),
		appleTouchIcon: resolve('appleTouchIcon', media?.apple_touch_icon_url, baseUrl),
		manifest: settingsState.data?.branding?.pwa_manifest_url
			? String(settingsState.data.branding.pwa_manifest_url)
			: null,
		sidebarLogo: resolve('sidebarLogo', media?.sidebar_logo_url, baseUrl),
		splashLogo: resolve('splashLogo', media?.splash_logo_url, baseUrl),
	}
}
