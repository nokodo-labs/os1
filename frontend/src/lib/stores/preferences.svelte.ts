import { browser } from '$app/environment'
import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { session } from '$lib/stores/session.svelte'
import { settingsState } from '$lib/stores/settings.svelte'

type UserPreferences = components['schemas']['UserPreferences']
type AppearancePreferences = components['schemas']['AppearancePreferences']
type AIPreferences = components['schemas']['AIPreferences']
type NotificationPreferences = components['schemas']['NotificationPreferences']
type PrivacyPreferences = components['schemas']['PrivacyPreferences']
type AccessibilityPreferences = components['schemas']['AccessibilityPreferences']

export type {
	AccessibilityPreferences,
	AIPreferences,
	AppearancePreferences,
	NotificationPreferences,
	PrivacyPreferences,
	UserPreferences,
}

export type ThemeMode = NonNullable<AppearancePreferences['themeMode']>
export type AccentColor = NonNullable<AppearancePreferences['accent']>
export type BackgroundType = NonNullable<AppearancePreferences['background']>

type Resolved = {
	appearance: Required<AppearancePreferences>
	ai: Required<AIPreferences>
	notifications: Required<NotificationPreferences>
	privacy: Required<PrivacyPreferences>
	accessibility: Required<AccessibilityPreferences>
}

const STORAGE_KEY = 'user-preferences:'

// ────────────────────────────────────────────────────────────
// utils
// ────────────────────────────────────────────────────────────

function isObject(v: unknown): v is Record<string, unknown> {
	return v !== null && typeof v === 'object' && !Array.isArray(v)
}

function merge<T extends Record<string, unknown>>(a: T, b: Partial<T>): T {
	const out = { ...a }
	for (const k in b) {
		const bVal = b[k]
		if (bVal === undefined) continue
		const aVal = a[k]
		out[k] =
			isObject(aVal) && isObject(bVal)
				? merge(aVal, bVal as Partial<typeof aVal>)
				: (bVal as T[typeof k])
	}
	return out
}

function readStorage(userId: string): UserPreferences {
	if (!browser) return {}
	try {
		const raw = localStorage.getItem(`${STORAGE_KEY}${userId}`)
		if (!raw) return {}
		const parsed = JSON.parse(raw)
		return isObject(parsed) ? (parsed as UserPreferences) : {}
	} catch {
		return {}
	}
}

function writeStorage(userId: string, prefs: UserPreferences): void {
	if (!browser) return
	try {
		localStorage.setItem(`${STORAGE_KEY}${userId}`, JSON.stringify(prefs))
	} catch {
		// ignore storage errors (quota, etc)
	}
}

// ────────────────────────────────────────────────────────────
// store
// ────────────────────────────────────────────────────────────

function createPreferencesStore() {
	let raw = $state<UserPreferences>({})
	let loading = $state(false)
	let error = $state<string | null>(null)
	let userId = $state<string | null>(null)

	// defaults: admin settings → hardcoded fallbacks
	// only ui.default_theme and ai.default_agent_id have admin settings
	const defaults: Resolved = $derived({
		appearance: {
			themeMode: (settingsState.data?.ui?.default_theme as ThemeMode) ?? 'system',
			accent: 'purple',
			background: 'darkveil',
		},
		ai: {
			defaultAgentId: settingsState.data?.ai?.default_agent_id ?? null,
		},
		notifications: {
			enabled: true,
			sound: true,
		},
		privacy: {
			saveHistory: true,
			shareUsageData: false,
		},
		accessibility: {
			hapticFeedback: true,
		},
	})

	// user preferences → defaults (which already include admin settings)
	const data: Resolved = $derived(merge(structuredClone(defaults), raw as Partial<Resolved>))

	// ──────────────────────────────────────────────────────
	// auto-sync with session
	// ──────────────────────────────────────────────────────

	function startSync(): () => void {
		// $effect.root lets us run effects outside component context
		const cleanup = $effect.root(() => {
			$effect(() => {
				const user = session.currentUser

				if (!user) {
					raw = {}
					userId = null
					error = null
					return
				}

				// user changed
				if (userId !== user.id) {
					userId = user.id

					// instant hydrate from localStorage
					let stored = readStorage(user.id)

					// session preferences override
					if (user.preferences) {
						stored = user.preferences
						writeStorage(user.id, stored)
					}

					raw = stored

					// then fetch fresh from API (no await, just fire)
					refresh()
				}
			})
		})

		return cleanup
	}

	// ──────────────────────────────────────────────────────
	// api
	// ──────────────────────────────────────────────────────

	async function refresh(): Promise<void> {
		const uid = userId
		if (!uid) return

		loading = true
		error = null

		try {
			const { data: res, error: err } = await apiClient().GET('/v1/users/{user_id}', {
				params: { path: { user_id: uid } },
			})

			if (err || !res) {
				error = 'could not load preferences'
				return
			}

			const fetched = (res.preferences ?? {}) as UserPreferences
			raw = fetched
			writeStorage(uid, fetched)
			session.currentUser = { ...res }
		} finally {
			loading = false
		}
	}

	async function update<K extends keyof UserPreferences>(
		section: K,
		updates: Partial<NonNullable<UserPreferences[K]>>
	): Promise<boolean> {
		const uid = userId
		if (!uid) return false

		// snapshot for rollback
		const prevRaw = raw

		// optimistic
		const nextRaw: UserPreferences = {
			...raw,
			[section]: { ...(raw[section] ?? {}), ...updates },
		}
		raw = nextRaw
		writeStorage(uid, nextRaw)
		error = null

		const { data: res, error: err } = await apiClient().PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { preferences: nextRaw },
		})

		if (err || !res) {
			// rollback
			raw = prevRaw
			writeStorage(uid, prevRaw)
			error = 'could not save preferences'
			return false
		}

		// server is truth
		const saved = (res.preferences ?? {}) as UserPreferences
		raw = saved
		writeStorage(uid, saved)
		session.currentUser = { ...res }

		return true
	}

	return {
		// state (reactive getters)
		get data() {
			return data
		},
		get loading() {
			return loading
		},
		get error() {
			return error
		},

		// methods
		startSync,
		refresh,
		update,
	}
}

export const preferences = createPreferencesStore()
