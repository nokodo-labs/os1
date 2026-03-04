/**
 * canonical application initialization module.
 * this is THE SINGLE entry point for all app startup logic.
 *
 * order of operations:
 * 1. init device/PWA state (sync, browser-only)
 * 2. ensure API origin is configured
 * 3. attempt token refresh (restore session) - throws BackendUnreachableError if network is down
 * 4. mark auth as ready (unblocks API requests)
 * 5. concurrently fetch all critical data (user, settings)
 * 6. connect event stream + start preference sync
 *
 * if the backend is unreachable at any point, returns { backendUnreachable: true } so the
 * layout can show a reconnect screen instead of a broken page or a useless login redirect.
 *
 * the splash screen stays up until initApp completes via appReadiness blocker.
 * call initApp() once from the root layout's onMount.
 */

import { browser } from '$app/environment'
import { BackendUnreachableError, refreshAccessToken } from '$lib/api/client'
import { apiOriginReady } from '$lib/api/origin'
import { eventStreamClient } from '$lib/api/streaming'
import { getAccessToken, markAuthReady } from '$lib/auth/session.svelte'
import { appReadiness } from '$lib/stores/appReadiness.svelte'
import { initDevice, requestGeolocation } from '$lib/stores/device.svelte'
import { initInstallPrompt } from '$lib/stores/installPrompt.svelte'
import { initNetwork } from '$lib/stores/network.svelte'
import { preferences } from '$lib/stores/preferences.svelte'
import { initServiceWorker } from '$lib/stores/serviceWorker.svelte'
import { session } from '$lib/stores/session.svelte'
import { loadSettings } from '$lib/stores/settings.svelte'

export interface InitResult {
	authenticated: boolean
	token: string | null
	backendUnreachable?: boolean
}

/**
 * initializes the application.
 * handles auth restoration, settings loading, and event stream connection.
 * holds the splash screen via an appReadiness blocker until all critical
 * data is loaded - no visual pops.
 *
 * @param options.skipAuthRestore - skip token refresh (e.g., on 404 pages)
 * @returns whether user is authenticated and their token
 */
export async function initApp(options?: { skipAuthRestore?: boolean }): Promise<InitResult> {
	if (!browser) {
		return { authenticated: false, token: null }
	}

	const initBlocker = appReadiness.createBlocker()

	try {
		// 1. sync device/PWA state (browser-only, after hydration)
		initDevice()
		initNetwork()
		initServiceWorker()
		initInstallPrompt()

		// 2. ensure API origin is configured
		await apiOriginReady

		// 3. restore session from refresh token cookie
		let token = getAccessToken()
		if (!options?.skipAuthRestore && !token) {
			try {
				token = await refreshAccessToken()
			} catch (err) {
				if (err instanceof BackendUnreachableError) {
					// backend is down - still mark auth ready so we don't deadlock,
					// then signal the layout to show the reconnect screen.
					markAuthReady()
					return { authenticated: false, token: null, backendUnreachable: true }
				}
				throw err
			}
		}

		// 4. unblock authenticated API requests
		markAuthReady()

		// 5. concurrently load all critical data.
		//    settings are public (loaded regardless of auth).
		//    user data + event stream only when authenticated.
		if (token) {
			try {
				await Promise.all([session.refreshUser(), loadSettings()])
			} catch (err) {
				if (err instanceof BackendUnreachableError) {
					return { authenticated: false, token: null, backendUnreachable: true }
				}
				throw err
			}

			// 6. event stream + preferences (needs user data from step 5)
			eventStreamClient.connect()
			preferences.startSync()

			// 7. request geolocation if user has useLocation enabled
			if (preferences.data.privacy.useLocation) {
				requestGeolocation()
			}
		} else {
			await loadSettings()
		}

		return {
			authenticated: Boolean(token),
			token,
		}
	} finally {
		initBlocker.done()
	}
}
