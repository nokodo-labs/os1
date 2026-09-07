/**
 * when cached data is re-read after a gap.
 *
 * the cache is stale exactly when the websocket could not deliver, so nothing
 * but the socket decides: a drop off `connected` opens the gap, the reconnect
 * closes it and refreshes every already-loaded store through the registry.
 * resume signals (tab visible, network back, bfcache restore, a frozen event
 * loop) only probe the socket - they never declare a gap themselves, and a
 * hidden stretch of any length is not one.
 */

import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

type StatusHandler = (next: string, previous: string) => void

const registry = vi.hoisted(() => ({
	loaded: {
		id: 'loaded',
		invalidate: vi.fn(),
		shouldRefresh: vi.fn(() => true),
		refresh: vi.fn(() => Promise.resolve()),
		clear: vi.fn(),
	},
	unloaded: {
		id: 'unloaded',
		invalidate: vi.fn(),
		shouldRefresh: vi.fn(() => false),
		refresh: vi.fn(() => Promise.resolve()),
		clear: vi.fn(),
	},
	preferences: { id: 'preferences', refresh: vi.fn(() => Promise.resolve()) },
}))

const stream = vi.hoisted(() => {
	const statusHandlers: StatusHandler[] = []
	return {
		statusHandlers,
		connect: vi.fn(),
		probe: vi.fn(),
		onStatusChange: vi.fn((handler: StatusHandler) => {
			statusHandlers.push(handler)
			return () => {}
		}),
	}
})

vi.mock('$app/environment', () => ({ browser: true }))
vi.mock('$lib/api/streaming', () => ({ eventStreamClient: stream }))
vi.mock('$lib/api/client', () => ({
	BackendUnreachableError: class BackendUnreachableError extends Error {},
	refreshAccessToken: vi.fn(),
}))
vi.mock('$lib/api/origin', () => ({ apiOriginReady: Promise.resolve() }))
vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	markAuthReady: vi.fn(),
}))
vi.mock('$lib/auth/sessionRevocation', () => ({ startSessionRevocationWatch: vi.fn() }))
vi.mock('$lib/stores/apiCacheRegistry', () => ({
	apiCacheStores: [registry.loaded, registry.unloaded],
	resumeRefreshStores: [registry.preferences],
}))
vi.mock('$lib/stores/appReadiness.svelte', () => ({
	appReadiness: { createBlocker: () => ({ done: vi.fn() }) },
}))
vi.mock('$lib/stores/device.svelte', () => ({
	initDevice: vi.fn(),
	requestGeolocation: vi.fn(),
}))
vi.mock('$lib/stores/installPrompt.svelte', () => ({ initInstallPrompt: vi.fn() }))
vi.mock('$lib/stores/network.svelte', () => ({ initNetwork: vi.fn() }))
vi.mock('$lib/stores/preferences.svelte', () => ({
	preferences: {
		startSync: vi.fn(),
		refresh: vi.fn(() => Promise.resolve()),
		data: { privacy: { useLocation: false } },
	},
}))
vi.mock('$lib/stores/pushNotifications.svelte', () => ({ initPushNotifications: vi.fn() }))
vi.mock('$lib/stores/serviceWorker.svelte', () => ({ initServiceWorker: vi.fn() }))
vi.mock('$lib/stores/session.svelte', () => ({
	session: { refreshUser: vi.fn(() => Promise.resolve()) },
}))
vi.mock('$lib/stores/settings.svelte', () => ({ loadSettings: vi.fn(() => Promise.resolve()) }))
vi.mock('$lib/stores/userClient.svelte', () => ({ initUserClient: vi.fn() }))

const TICK_MS = 5_000

async function flush(): Promise<void> {
	for (let i = 0; i < 5; i++) await Promise.resolve()
}

function setVisibility(state: 'visible' | 'hidden'): void {
	Object.defineProperty(document, 'visibilityState', { configurable: true, value: state })
}

function fireVisibilityChange(): void {
	document.dispatchEvent(new Event('visibilitychange'))
}

function fireRestoredFromBfcache(): void {
	const event = new Event('pageshow')
	Object.defineProperty(event, 'persisted', { configurable: true, value: true })
	window.dispatchEvent(event)
}

let statusChanged: StatusHandler

describe('resuming live data after a gap', () => {
	beforeAll(async () => {
		vi.useFakeTimers()
		const { initAuthenticatedSession } = await import('$lib/init')
		await initAuthenticatedSession()
		statusChanged = stream.statusHandlers[0]
	})

	afterAll(() => {
		vi.useRealTimers()
	})

	beforeEach(async () => {
		// settle the frozen-loop watchdog and close any gap a prior test opened
		vi.advanceTimersByTime(TICK_MS * 2)
		statusChanged('connected', 'connecting')
		await flush()
		setVisibility('visible')
		vi.clearAllMocks()
	})

	it('registers exactly one status listener for the whole session', () => {
		expect(stream.statusHandlers).toHaveLength(1)
	})

	it('refreshes the loaded stores through the registry when the socket comes back', async () => {
		statusChanged('reconnecting', 'connected')
		expect(registry.loaded.invalidate).toHaveBeenCalledTimes(1)
		expect(registry.loaded.refresh).not.toHaveBeenCalled()

		statusChanged('connected', 'reconnecting')
		await flush()

		expect(registry.loaded.refresh).toHaveBeenCalledTimes(1)
		expect(registry.preferences.refresh).toHaveBeenCalledTimes(1)
	})

	it('leaves a store nothing has read yet alone', async () => {
		statusChanged('reconnecting', 'connected')
		statusChanged('connected', 'reconnecting')
		await flush()

		expect(registry.unloaded.shouldRefresh).toHaveBeenCalled()
		expect(registry.unloaded.refresh).not.toHaveBeenCalled()
	})

	it('does not refresh on the first connect of a boot', async () => {
		statusChanged('connected', 'connecting')
		await flush()

		expect(registry.loaded.refresh).not.toHaveBeenCalled()
		expect(registry.preferences.refresh).not.toHaveBeenCalled()
	})

	it('probes but does not refresh when the tab comes back to a live socket', async () => {
		setVisibility('hidden')
		fireVisibilityChange()
		setVisibility('visible')
		fireVisibilityChange()
		await flush()

		expect(stream.probe).toHaveBeenCalledTimes(1)
		expect(registry.loaded.invalidate).not.toHaveBeenCalled()
		expect(registry.loaded.refresh).not.toHaveBeenCalled()
	})

	it('refreshes only once the probe finds a zombie socket and reconnects', async () => {
		// a zombie socket answers no pong: the client forces a reconnect, which is
		// the drop that opens the gap
		stream.probe.mockImplementationOnce(() => statusChanged('reconnecting', 'connected'))

		fireVisibilityChange()
		await flush()
		expect(registry.loaded.refresh).not.toHaveBeenCalled()

		statusChanged('connected', 'reconnecting')
		await flush()

		expect(registry.loaded.refresh).toHaveBeenCalledTimes(1)
	})

	it('never refreshes on hidden time alone, however long', async () => {
		setVisibility('hidden')
		fireVisibilityChange()
		vi.setSystemTime(Date.now() + 30 * 60_000)
		setVisibility('visible')
		fireVisibilityChange()
		await flush()

		expect(stream.probe).toHaveBeenCalledTimes(1)
		expect(registry.loaded.invalidate).not.toHaveBeenCalled()
		expect(registry.loaded.refresh).not.toHaveBeenCalled()
		expect(registry.preferences.refresh).not.toHaveBeenCalled()
	})

	it('probes on network recovery and on a bfcache restore', async () => {
		window.dispatchEvent(new Event('online'))
		fireRestoredFromBfcache()
		await flush()

		expect(stream.probe).toHaveBeenCalledTimes(2)
		expect(registry.loaded.refresh).not.toHaveBeenCalled()
	})

	it('probes when the event loop was frozen instead of assuming a gap', async () => {
		vi.setSystemTime(Date.now() + 60_000)
		vi.advanceTimersByTime(TICK_MS)
		await flush()

		expect(stream.probe).toHaveBeenCalledTimes(1)
		expect(registry.loaded.invalidate).not.toHaveBeenCalled()
		expect(registry.loaded.refresh).not.toHaveBeenCalled()
	})
})
