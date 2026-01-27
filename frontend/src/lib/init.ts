/**
 * canonical application initialization module.
 * this is THE SINGLE entry point for all app startup logic.
 *
 * order of operations:
 * 1. ensure API origin is configured
 * 2. attempt token refresh (restore session)
 * 3. mark auth as ready (unblocks API requests)
 * 4. load user settings (if authenticated)
 * 5. connect event stream (if authenticated)
 *
 * call initApp() once from the root layout's onMount.
 */

import { browser } from '$app/environment'
import { refreshAccessToken } from '$lib/api/client'
import { apiOriginReady } from '$lib/api/origin'
import { eventStreamClient } from '$lib/api/streaming'
import { getAccessToken, markAuthReady } from '$lib/auth/session.svelte'
import { loadSettings } from '$lib/stores/settings.svelte'

export interface InitResult {
	authenticated: boolean
	token: string | null
}

/**
 * initializes the application.
 * handles auth restoration, settings loading, and event stream connection.
 *
 * @param options.skipAuthRestore - skip token refresh (e.g., on 404 pages)
 * @returns whether user is authenticated and their token
 */
export async function initApp(options?: { skipAuthRestore?: boolean }): Promise<InitResult> {
	if (!browser) {
		return { authenticated: false, token: null }
	}

	// 1. ensure API origin is ready
	await apiOriginReady

	// 2. attempt to restore session from refresh token
	let token = getAccessToken()
	if (!options?.skipAuthRestore && !token) {
		token = await refreshAccessToken()
	}

	// 3. mark auth as ready (unblocks any waiting API requests)
	markAuthReady()

	// 4 & 5. if authenticated, load settings and connect event stream
	if (token) {
		void loadSettings()
		eventStreamClient.connect()
	}

	return {
		authenticated: Boolean(token),
		token,
	}
}
