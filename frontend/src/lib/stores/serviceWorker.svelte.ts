/**
 * service worker update detection.
 *
 * registration is handled natively by SvelteKit.
 * this module detects when a new version is waiting
 * and exposes a reactive flag + apply function.
 *
 * call initServiceWorker() once during app init.
 */

import { browser } from '$app/environment'

const UPDATE_CHECK_INTERVAL = 5 * 60 * 1000 // 5 minutes
const UPDATE_CHECK_MIN_GAP = 10 * 1000

export const swUpdate = $state({
	updateAvailable: false,
	checkingForUpdate: false,
	applyingUpdate: false,
	updateError: null as string | null,
})

let registration: ServiceWorkerRegistration | null = null
let trackedRegistration: ServiceWorkerRegistration | null = null
let didInit = false
let reloading = false
let updateInFlight: Promise<void> | null = null
let lastUpdateCheckAt = 0
let updateTimer: ReturnType<typeof setInterval> | null = null
let registrationCleanup: (() => void) | null = null
let cleanup: (() => void) | null = null
const watchedWorkers = new WeakSet<ServiceWorker>()

/** check if a SW is already waiting, accounting for race conditions */
function watchInstalling(sw: ServiceWorker): void {
	if (watchedWorkers.has(sw)) return
	watchedWorkers.add(sw)

	// if it already reached 'installed', we might have missed the statechange event
	if (sw.state === 'installed' && navigator.serviceWorker.controller) {
		swUpdate.updateAvailable = true
		return
	}
	sw.addEventListener('statechange', () => {
		if (sw.state === 'installed' && navigator.serviceWorker.controller) {
			swUpdate.updateAvailable = true
		}
	})
}

/** inspect a registration and sync update availability state. */
function inspectRegistration(reg: ServiceWorkerRegistration): void {
	let hasUpdateCandidate = false
	if (reg.waiting && navigator.serviceWorker.controller) {
		swUpdate.updateAvailable = true
		hasUpdateCandidate = true
	}
	if (reg.installing) {
		watchInstalling(reg.installing)
		hasUpdateCandidate = true
	}
	if (!hasUpdateCandidate) {
		swUpdate.updateAvailable = false
	}
}

/** attach listeners for one registration and cache it for later checks. */
function trackRegistration(reg: ServiceWorkerRegistration): void {
	registration = reg
	inspectRegistration(reg)
	if (trackedRegistration === reg) return

	registrationCleanup?.()
	trackedRegistration = reg

	const onUpdateFound = () => {
		const installing = reg.installing
		if (!installing) return
		watchInstalling(installing)
	}

	reg.addEventListener('updatefound', onUpdateFound)
	registrationCleanup = () => {
		reg.removeEventListener('updatefound', onUpdateFound)
	}
}

/** load the active service worker registration, if the browser has one. */
async function refreshRegistration(): Promise<ServiceWorkerRegistration | null> {
	const reg = await navigator.serviceWorker.getRegistration()
	if (!reg) return null
	trackRegistration(reg)
	return reg
}

/** convert an unknown update failure into a displayable message. */
function updateErrorMessage(error: unknown): string {
	if (error instanceof Error && error.message) return error.message
	return 'service worker update check failed'
}

/** check whether a newer service worker has installed or can be fetched. */
function checkForUpdate(force = false): Promise<void> {
	const now = Date.now()
	if (!force && now - lastUpdateCheckAt < UPDATE_CHECK_MIN_GAP) {
		return updateInFlight ?? Promise.resolve()
	}
	if (updateInFlight) return updateInFlight
	lastUpdateCheckAt = now
	swUpdate.checkingForUpdate = true
	swUpdate.updateError = null

	updateInFlight = (async () => {
		const reg = registration ?? (await refreshRegistration())
		if (!reg) return
		inspectRegistration(reg)
		if (reg.waiting) return
		try {
			await reg.update()
			inspectRegistration(reg)
		} catch (error) {
			// update checks are opportunistic; failures are retried on the next trigger.
			swUpdate.updateError = updateErrorMessage(error)
		}
	})().finally(() => {
		swUpdate.checkingForUpdate = false
		updateInFlight = null
	})
	return updateInFlight
}

/** initialize service worker update tracking for this tab. */
export function initServiceWorker(): void {
	if (!browser || didInit) return
	if (!('serviceWorker' in navigator)) return
	didInit = true

	const onControllerChange = () => {
		if (reloading) return
		reloading = true
		window.location.reload()
	}

	// SvelteKit registers the service worker natively.
	// we hook into the registration to detect updates, including events that happen
	// before serviceWorker.ready resolves.
	refreshRegistration()
		.then((reg) => {
			if (reg) void checkForUpdate(true)
		})
		.catch(() => {})

	navigator.serviceWorker.ready
		.then((reg) => {
			trackRegistration(reg)
			void checkForUpdate(true)

			// periodic update check for long-lived tabs
			updateTimer = setInterval(() => {
				void checkForUpdate()
			}, UPDATE_CHECK_INTERVAL)
		})
		.catch((err) => {
			console.warn('service worker ready failed:', err)
		})

	// check for updates when tab regains focus (user returns from another tab/app)
	const onVisibilityChange = () => {
		if (document.visibilityState === 'visible') void checkForUpdate()
	}
	const onWindowFocus = () => void checkForUpdate()
	const onOnline = () => void checkForUpdate()
	const onPageShow = () => void checkForUpdate()

	document.addEventListener('visibilitychange', onVisibilityChange)
	window.addEventListener('focus', onWindowFocus)
	window.addEventListener('online', onOnline)
	window.addEventListener('pageshow', onPageShow)

	navigator.serviceWorker.addEventListener('controllerchange', onControllerChange)

	cleanup = () => {
		navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange)
		document.removeEventListener('visibilitychange', onVisibilityChange)
		window.removeEventListener('focus', onWindowFocus)
		window.removeEventListener('online', onOnline)
		window.removeEventListener('pageshow', onPageShow)
		registrationCleanup?.()
		registrationCleanup = null
		if (updateTimer) {
			clearInterval(updateTimer)
			updateTimer = null
		}
	}

	if (import.meta.hot) {
		import.meta.hot.dispose(() => destroyServiceWorker())
	}
}

/** tell the waiting service worker to skip waiting and activate. */
export async function applyUpdate(): Promise<void> {
	if (swUpdate.applyingUpdate) return
	swUpdate.applyingUpdate = true
	swUpdate.updateError = null

	try {
		const reg = registration ?? (await refreshRegistration())
		if (!reg?.waiting) {
			swUpdate.updateAvailable = false
			await checkForUpdate(true)
			return
		}
		reg.waiting.postMessage({ type: 'SKIP_WAITING' })
	} catch (error) {
		swUpdate.updateError = updateErrorMessage(error)
	} finally {
		swUpdate.applyingUpdate = false
	}
}

/** remove service worker update listeners and reset local state. */
export function destroyServiceWorker(): void {
	cleanup?.()
	cleanup = null
	didInit = false
	reloading = false
	registration = null
	trackedRegistration = null
	updateInFlight = null
	lastUpdateCheckAt = 0
	swUpdate.updateAvailable = false
	swUpdate.checkingForUpdate = false
	swUpdate.applyingUpdate = false
	swUpdate.updateError = null
}
