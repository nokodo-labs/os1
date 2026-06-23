import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { onAccessTokenChanged } from '$lib/auth/session.svelte'
import { STORE_EVENT_TYPES, subscribeToStoreEvents } from '$lib/stores/storeEvents'
import { deepMerge, isPlainObject } from '$lib/utils'

type Settings = components['schemas']['Settings']
type SettingsPatch = components['schemas']['SettingsPatch']
type SettingsVersions = components['schemas']['SettingsVersions']

const DEFAULT_CACHE_TTL_MS = 5 * 60 * 1000

export const settingsState = $state({
	ready: false,
	loading: false,
	error: null as string | null,
	data: null as Settings | null,
	versions: null as SettingsVersions | null,
	fetchedAt: 0,
	stale: true,
})

let inFlight: Promise<Settings | null> | null = null

function isFresh(fetchedAt: number, maxAgeMs: number): boolean {
	return Date.now() - fetchedAt < maxAgeMs
}

export function invalidateSettings(): void {
	settingsState.stale = true
}

export function clearSettings(): void {
	settingsState.ready = false
	settingsState.loading = false
	settingsState.error = null
	settingsState.data = null
	settingsState.versions = null
	settingsState.fetchedAt = 0
	settingsState.stale = true
}

/**
	apply a partial update to the cached settings without refetching.

	intended usage: SSE/event-stream settings update events.
*/
export function applySettingsPatch(
	patch: SettingsPatch,
	options?: {
		versions?: SettingsVersions
		markFresh?: boolean
		applyNulls?: boolean
	}
): void {
	if (!settingsState.data) {
		settingsState.stale = true
		return
	}
	if (!isPlainObject(patch)) {
		settingsState.stale = true
		return
	}

	settingsState.data = deepMerge(
		settingsState.data as Record<string, unknown>,
		patch as Record<string, unknown>,
		{ applyNulls: options?.applyNulls ?? false }
	) as Settings

	if (options?.versions) {
		settingsState.versions = options.versions
	}

	if (options?.markFresh ?? true) {
		settingsState.fetchedAt = Date.now()
		settingsState.stale = false
		settingsState.ready = true
	}
}

export function applySettingsSnapshot(snapshot: Settings, versions: SettingsVersions): void {
	settingsState.data = snapshot
	settingsState.versions = versions
	settingsState.fetchedAt = Date.now()
	settingsState.ready = true
	settingsState.stale = false
}

export async function loadSettings(options?: {
	force?: boolean
	maxAgeMs?: number
}): Promise<Settings | null> {
	const force = options?.force ?? false
	const maxAgeMs = options?.maxAgeMs ?? DEFAULT_CACHE_TTL_MS

	if (inFlight) return inFlight

	if (!force && settingsState.data && !settingsState.stale) {
		if (isFresh(settingsState.fetchedAt, maxAgeMs)) return settingsState.data
	}

	inFlight = (async () => {
		settingsState.loading = true
		settingsState.error = null

		try {
			const { data, error, response } = await api.GET('/v1/settings', {})
			if (error || !response.ok || !data) {
				settingsState.error = 'could not load settings'
				settingsState.stale = true
				return null
			}

			settingsState.data = data.data
			settingsState.versions = data.versions
			settingsState.fetchedAt = Date.now()
			settingsState.ready = true
			settingsState.stale = false
			return settingsState.data
		} catch {
			settingsState.error = 'could not load settings'
			settingsState.stale = true
			return null
		} finally {
			settingsState.loading = false
		}
	})()

	try {
		return await inFlight
	} finally {
		inFlight = null
	}
}

export async function refreshSettings(): Promise<Settings | null> {
	return await loadSettings({ force: true })
}

export const settingsCache = {
	invalidate: invalidateSettings,
	refresh: refreshSettings,
	clear: clearSettings,
}

// event stream integration

let settingsUnsub: (() => void) | null = null

function handleSettingsEvent(): void {
	// settings updated (any session, including this one) - refetch
	void loadSettings({ force: true })
}

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			if (!settingsUnsub) {
				settingsUnsub = subscribeToStoreEvents(
					STORE_EVENT_TYPES.settings,
					handleSettingsEvent
				)
			}
		} else {
			settingsUnsub?.()
			settingsUnsub = null
			clearSettings()
		}
	})
}
