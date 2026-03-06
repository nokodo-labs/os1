/**
 * reactive network connectivity state.
 *
 * tracks online/offline via navigator.onLine + events.
 * call initNetwork() once from the root layout's onMount.
 */

import { browser } from '$app/environment'

export const network = $state({
	online: true,
})

let didInit = false
let cleanup: (() => void) | null = null

export function initNetwork(): void {
	if (!browser || didInit) return
	didInit = true

	network.online = navigator.onLine

	const onOnline = () => {
		network.online = true
	}
	const onOffline = () => {
		network.online = false
	}

	window.addEventListener('online', onOnline)
	window.addEventListener('offline', onOffline)

	cleanup = () => {
		window.removeEventListener('online', onOnline)
		window.removeEventListener('offline', onOffline)
	}

	if (import.meta.hot) {
		import.meta.hot.dispose(() => {
			destroyNetwork()
		})
	}
}

export function destroyNetwork(): void {
	cleanup?.()
	cleanup = null
	didInit = false
	network.online = true
}
