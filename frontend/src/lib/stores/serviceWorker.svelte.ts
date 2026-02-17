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

const UPDATE_CHECK_INTERVAL = 30 * 60 * 1000 // 30 minutes

export const swUpdate = $state({
	updateAvailable: false,
})

let registration: ServiceWorkerRegistration | null = null
let didInit = false
let reloading = false
let updateTimer: ReturnType<typeof setInterval> | null = null
let cleanup: (() => void) | null = null

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
	// we just hook into the registration to detect updates.
	navigator.serviceWorker.ready
		.then((reg) => {
			registration = reg

			// a new SW is already waiting (e.g. user revisited after deploy)
			if (reg.waiting) {
				swUpdate.updateAvailable = true
			}

			// new SW installed while page is open
			reg.addEventListener('updatefound', () => {
				const installing = reg.installing
				if (!installing) return

				installing.addEventListener('statechange', () => {
					if (installing.state === 'installed' && navigator.serviceWorker.controller) {
						swUpdate.updateAvailable = true
					}
				})
			})

			// periodic update check for long-lived tabs
			updateTimer = setInterval(() => {
				reg.update().catch(() => {})
			}, UPDATE_CHECK_INTERVAL)
		})
		.catch((err) => {
			console.warn('service worker ready failed:', err)
		})

	navigator.serviceWorker.addEventListener('controllerchange', onControllerChange)

	cleanup = () => {
		navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange)
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
export function applyUpdate(): void {
	if (registration?.waiting) {
		registration.waiting.postMessage({ type: 'SKIP_WAITING' })
	}
}

export function destroyServiceWorker(): void {
	cleanup?.()
	cleanup = null
	didInit = false
	reloading = false
	registration = null
	swUpdate.updateAvailable = false
}
