/**
 * PWA install prompt (A2HS) state.
 *
 * captures the beforeinstallprompt event, detects installed state,
 * and exposes a reactive prompt trigger.
 *
 * call initInstallPrompt() once during app init.
 */

import { browser } from '$app/environment'
import { device } from '$lib/stores/device.svelte'

const DISMISS_KEY = 'pwa-install-dismissed'
const DISMISS_TTL_MS = 30 * 24 * 60 * 60 * 1000 // 30 days

export const installPrompt = $state({
	/** whether the browser can show an install prompt. */
	canInstall: false,
	/** whether the app is already installed. */
	isInstalled: false,
	/** whether the user has dismissed the prompt. */
	dismissed: false,
})

let deferredPrompt: BeforeInstallPromptEvent | null = null
let didInit = false
let cleanup: (() => void) | null = null

interface BeforeInstallPromptEvent extends Event {
	prompt: () => Promise<void>
	userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/** check whether the dismiss flag is still within the TTL window. */
function isDismissed(): boolean {
	const raw = localStorage.getItem(DISMISS_KEY)
	if (!raw) return false
	const ts = Number(raw)
	if (Number.isNaN(ts)) return false
	return Date.now() - ts < DISMISS_TTL_MS
}

export function initInstallPrompt(): void {
	if (!browser || didInit) return
	didInit = true

	installPrompt.isInstalled = device.pwaInstalled
	installPrompt.dismissed = isDismissed()

	const onBeforeInstall = (e: Event) => {
		e.preventDefault()
		deferredPrompt = e as BeforeInstallPromptEvent
		installPrompt.canInstall = true
	}

	const onAppInstalled = () => {
		installPrompt.isInstalled = true
		installPrompt.canInstall = false
		deferredPrompt = null
	}

	window.addEventListener('beforeinstallprompt', onBeforeInstall)
	window.addEventListener('appinstalled', onAppInstalled)

	cleanup = () => {
		window.removeEventListener('beforeinstallprompt', onBeforeInstall)
		window.removeEventListener('appinstalled', onAppInstalled)
	}

	if (import.meta.hot) {
		import.meta.hot.dispose(() => destroyInstallPrompt())
	}
}

/** trigger the native install prompt. */
export async function promptInstall(): Promise<void> {
	if (!deferredPrompt) return

	try {
		await deferredPrompt.prompt()
		const { outcome } = await deferredPrompt.userChoice

		if (outcome === 'accepted') {
			installPrompt.isInstalled = true
		}
		installPrompt.canInstall = false
		deferredPrompt = null
	} catch {
		installPrompt.canInstall = false
		deferredPrompt = null
	}
}

/** dismiss the install prompt and persist the choice with a TTL. */
export function dismissInstallPrompt(): void {
	installPrompt.dismissed = true
	localStorage.setItem(DISMISS_KEY, String(Date.now()))
}

export function destroyInstallPrompt(): void {
	cleanup?.()
	cleanup = null
	didInit = false
	deferredPrompt = null
	installPrompt.canInstall = false
	installPrompt.dismissed = false
	// intentionally leave isInstalled as-is — the app doesn't uninstall on HMR
}
