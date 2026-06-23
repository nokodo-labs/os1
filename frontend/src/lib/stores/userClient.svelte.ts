import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { device } from '$lib/stores/device.svelte'
import { session } from '$lib/stores/session.svelte'

type UserClient = components['schemas']['UserClient']
type UserClientUpsert = components['schemas']['UserClientUpsert']

type UserClientState = {
	clientKey: string | null
	current: UserClient | null
	loading: boolean
	ready: boolean
	error: string | null
}

const CLIENT_KEY_STORAGE_KEY = 'nokodo-ai:user-client-key:v1'

export const userClient: UserClientState = $state({
	clientKey: null,
	current: null,
	loading: false,
	ready: false,
	error: null,
})

let didInit = false
let cleanup: (() => void) | null = null
let inFlight: Promise<UserClient | null> | null = null
let registeredForUserId: string | null = null

function createClientKey(): string {
	if (crypto.randomUUID) return crypto.randomUUID()
	return `cli_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`
}

function getOrCreateClientKey(): string | null {
	if (!browser) return null
	const existing = window.localStorage.getItem(CLIENT_KEY_STORAGE_KEY)
	if (existing) {
		userClient.clientKey = existing
		return existing
	}
	const created = createClientKey()
	window.localStorage.setItem(CLIENT_KEY_STORAGE_KEY, created)
	userClient.clientKey = created
	return created
}

function buildClientName(): string {
	const parts = [device.browserName, device.os].filter(Boolean)
	return parts.length > 0 ? parts.join(' on ') : 'this client'
}

function buildClientInfo(): Record<string, unknown> {
	return {
		timezone: device.timezone,
		language: device.language,
		os: device.os,
		browser: device.browserName,
		pwaInstalled: device.pwaInstalled,
		displayMode: device.displayMode,
		isMobile: device.isMobile,
		isTouch: device.isTouch,
		isChromium: device.isChromium,
		screenWidth: device.width,
		screenHeight: device.height,
		viewportWidth: device.viewportWidth,
		viewportHeight: device.viewportHeight,
		dpr: device.dpr,
		preferredColorScheme: device.preferredColorScheme,
		prefersReducedMotion: device.prefersReducedMotion,
		prefersContrast: device.prefersContrast,
		connectionType: device.connectionType,
		connectionEffectiveType: device.connectionEffectiveType,
		connectionDownlinkMbps: device.connectionDownlinkMbps,
		connectionRttMs: device.connectionRttMs,
		connectionSaveData: device.connectionSaveData,
		batterySupported: device.batterySupported,
		batteryCharging: device.batteryCharging,
		batteryLevel: device.batteryLevel,
		gpuTier: device.gpuTier,
		gpuDiagnostics: device.gpuDiagnostics,
	}
}

export async function ensureUserClient(): Promise<UserClient | null> {
	if (!browser) return null
	if (inFlight) return inFlight

	const userId = session.currentUserId
	const clientKey = getOrCreateClientKey()
	if (!userId || !clientKey) return null

	inFlight = (async () => {
		userClient.loading = true
		userClient.error = null
		try {
			const body: UserClientUpsert = {
				client_key: clientKey,
				name: buildClientName(),
				user_agent: device.userAgent,
				info: buildClientInfo(),
			}
			const { data, error, response } = await api.POST('/v1/users/{user_id}/clients', {
				params: { path: { user_id: userId } },
				body,
			})
			if (error || !response.ok || !data) {
				userClient.error = 'could not register this client'
				userClient.ready = false
				return null
			}
			userClient.current = data
			userClient.ready = true
			registeredForUserId = userId
			return data
		} catch (error) {
			userClient.error =
				error instanceof Error ? error.message : 'could not register this client'
			userClient.ready = false
			return null
		} finally {
			userClient.loading = false
		}
	})()

	try {
		return await inFlight
	} finally {
		inFlight = null
	}
}

export function clearUserClient(): void {
	userClient.current = null
	userClient.loading = false
	userClient.ready = false
	userClient.error = null
	registeredForUserId = null
}

export function initUserClient(): void {
	if (!browser || didInit) return
	didInit = true
	userClient.clientKey = getOrCreateClientKey()

	const cleanupEffect = $effect.root(() => {
		$effect(() => {
			const userId = session.currentUserId
			const deviceReady = device.ready

			if (!userId) {
				clearUserClient()
				return
			}
			if (!deviceReady) return
			if (registeredForUserId === userId && userClient.current) return
			void ensureUserClient()
		})
	})

	cleanup = () => cleanupEffect()

	if (import.meta.hot) {
		import.meta.hot.dispose(() => destroyUserClient())
	}
}

export function destroyUserClient(): void {
	cleanup?.()
	cleanup = null
	didInit = false
	inFlight = null
	clearUserClient()
}
