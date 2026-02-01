import { loadPublicConfig } from '$lib/config/public'

import { setApiOrigin } from './client'

let initPromise: Promise<string | null> | null = null

/**
 * Initializes the API origin for cross-origin deployments.
 *
 * This must run before any API requests (including auth refresh and event streams).
 */
export async function initApiOrigin(): Promise<string | null> {
	if (initPromise) return initPromise

	initPromise = (async () => {
		const config = await loadPublicConfig()
		setApiOrigin(config.api_origin)
		return config.api_origin
	})()

	return initPromise
}
