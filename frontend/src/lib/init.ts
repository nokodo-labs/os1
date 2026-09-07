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
import { startSessionRevocationWatch } from '$lib/auth/sessionRevocation'
import { apiCacheStores, resumeRefreshStores } from '$lib/stores/apiCacheRegistry'
import { appReadiness } from '$lib/stores/appReadiness.svelte'
import { invalidateApiCacheStores, refreshLifecycleStores } from '$lib/stores/cacheLifecycle'
import { initDevice, requestGeolocation } from '$lib/stores/device.svelte'
import { initInstallPrompt } from '$lib/stores/installPrompt.svelte'
import { initNetwork } from '$lib/stores/network.svelte'
import { preferences } from '$lib/stores/preferences.svelte'
import { initPushNotifications } from '$lib/stores/pushNotifications.svelte'
import { initServiceWorker } from '$lib/stores/serviceWorker.svelte'
import { session } from '$lib/stores/session.svelte'
import { loadSettings } from '$lib/stores/settings.svelte'
import { initUserClient } from '$lib/stores/userClient.svelte'

export interface InitResult {
	authenticated: boolean
	token: string | null
	backendUnreachable?: boolean
}

const EXECUTION_TICK_MS = 5_000
/** a tick this late means the event loop was frozen (device sleep, app switch). */
const EXECUTION_TICK_JUMP_MS = EXECUTION_TICK_MS * 2
let cacheLifecycleStarted = false
let authSessionStarted = false
let lastExecutionTick = Date.now()
let missedLiveEvents = false

function hasSession(): boolean {
	return Boolean(getAccessToken())
}

/** a gap where live events could have been missed: the socket was not delivering. */
function markMissedLiveEvents(): void {
	missedLiveEvents = true
	if (!hasSession()) return
	invalidateApiCacheStores(apiCacheStores)
}

/**
 * re-read what stayed on screen across the gap.
 *
 * invalidation only marks caches stale, and a view that already loaded never
 * re-reads on its own - so the chat sidebar and the open thread would keep
 * rendering pre-gap data until the reader navigates. every registered store
 * swaps its data in place and leaves `hasLoaded` alone, so this shows no
 * skeletons; `shouldRefresh()` keeps it off the stores nothing has read yet.
 * `resumeRefreshStores` covers the stores nothing marks stale (preferences),
 * whose cross-session updates only ever arrive on the stream.
 */
function resumeLiveData(): void {
	if (!missedLiveEvents || !hasSession()) return
	missedLiveEvents = false
	void refreshLifecycleStores([...apiCacheStores, ...resumeRefreshStores])
}

/**
 * the cache is stale exactly when the socket could not deliver, so the socket
 * itself is the only thing that opens or closes a gap: any drop off `connected`
 * (close, or a pong timeout forcing a reconnect) opens one, and the reconnect
 * closes it. resume signals never decide staleness on their own - they only
 * probe, because the OS can kill a socket without a close event and leave a
 * zombie whose `readyState` still reads OPEN. the probe's pong timeout turns
 * that zombie into a real drop, which is what marks the gap.
 */
function startCacheLifecycle(): void {
	if (cacheLifecycleStarted || !browser) return
	cacheLifecycleStarted = true

	eventStreamClient.onStatusChange((newStatus, prevStatus) => {
		if (prevStatus === 'connected' && newStatus !== 'connected') {
			markMissedLiveEvents()
			return
		}
		// only a RE-connect closes a gap: the first connect of a boot has
		// nothing to catch up on, and resuming there would re-run the boot.
		if (newStatus === 'connected' && prevStatus !== 'connected') resumeLiveData()
	})

	const probeLiveStream = () => eventStreamClient.probe()

	window.addEventListener('online', probeLiveStream)
	window.addEventListener('pageshow', (event) => {
		if (event.persisted) probeLiveStream()
	})
	document.addEventListener('visibilitychange', () => {
		if (document.visibilityState === 'visible') probeLiveStream()
	})

	setInterval(() => {
		const now = Date.now()
		const frozen = now - lastExecutionTick > EXECUTION_TICK_JUMP_MS
		lastExecutionTick = now
		if (frozen) probeLiveStream()
	}, EXECUTION_TICK_MS)
}

/**
 * starts every authenticated-session service: critical data load, event
 * stream, preference sync, user client, push notifications, cache lifecycle,
 * and geolocation. safe to call once after startup token-restore (initApp) or
 * after an interactive login. re-entrant: a second call is a no-op so the
 * stream/sync are not started twice.
 *
 * throws BackendUnreachableError if the initial data load fails on a network
 * error so callers can show the reconnect screen.
 */
export async function initAuthenticatedSession(): Promise<void> {
	if (!browser || authSessionStarted) return
	authSessionStarted = true

	try {
		// concurrently load critical data (user + settings)
		await Promise.all([session.refreshUser(), loadSettings()])
	} catch (err) {
		// allow a later retry to start the session if the load failed
		authSessionStarted = false
		throw err
	}

	// event stream + preferences (needs user data from the load above)
	eventStreamClient.connect()
	startSessionRevocationWatch()
	preferences.startSync()
	initUserClient()
	initPushNotifications()

	// track live-stream gaps: caches go stale on a WS drop, refresh on reconnect
	startCacheLifecycle()

	// request geolocation if user has useLocation enabled
	if (preferences.data.privacy.useLocation) {
		requestGeolocation()
	}
}

/**
 * resets the authenticated-session guard so a subsequent interactive login
 * re-runs initAuthenticatedSession in full. call on logout: the SPA stays
 * mounted across logout -> login, so without this the guard stays latched and
 * the next login never refetches the user or settings.
 */
export function resetAuthenticatedSession(): void {
	authSessionStarted = false
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
				await initAuthenticatedSession()
			} catch (err) {
				if (err instanceof BackendUnreachableError) {
					return { authenticated: false, token: null, backendUnreachable: true }
				}
				throw err
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
