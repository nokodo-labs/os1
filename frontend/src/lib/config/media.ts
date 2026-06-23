/**
 * media asset URL resolution.
 *
 * each asset chooses one source: default, cdn, or custom.
 */

import { browser } from '$app/environment'
import { getApiBaseUrl } from '$lib/api/client'
import { settingsState } from '$lib/stores/settings.svelte'

/** resolved media URLs - reactive derivation from settings. */
export function getMediaUrls(): {
	favicon: string | null
	appleTouchIcon: string | null
	manifest: string | null
} {
	const media = settingsState.data?.media

	return {
		favicon: media?.favicon?.url ?? null,
		appleTouchIcon: media?.apple_touch_icon?.url ?? null,
		manifest: settingsState.data?.branding?.pwa_manifest_url
			? String(settingsState.data.branding.pwa_manifest_url)
			: browser
				? `${getApiBaseUrl()}/system/manifest.json`
				: null,
	}
}
