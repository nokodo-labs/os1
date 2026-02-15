import { browser } from '$app/environment'
import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { device } from '$lib/stores/device.svelte'
import { session } from '$lib/stores/session.svelte'
import { settingsState } from '$lib/stores/settings.svelte'
import { deepMerge, isPlainObject } from '$lib/utils'

type UserPreferences = components['schemas']['UserPreferences']
type AppearancePreferences = components['schemas']['AppearancePreferences']
type AccountPreferences = components['schemas']['AccountPreferences']
type AIPreferences = components['schemas']['AIPreferences']
type NotificationPreferences = components['schemas']['NotificationPreferences']
type PrivacyPreferences = components['schemas']['PrivacyPreferences']
type AccessibilityPreferences = components['schemas']['AccessibilityPreferences']

export type {
	AccessibilityPreferences,
	AccountPreferences,
	AIPreferences,
	AppearancePreferences,
	NotificationPreferences,
	PrivacyPreferences,
	UserPreferences,
}

export type ThemeMode = NonNullable<AppearancePreferences['themeMode']>
export type AccentColor = NonNullable<AppearancePreferences['accent']>
export type BackgroundType = NonNullable<AppearancePreferences['background']>
export type BubbleTailStyle = NonNullable<AppearancePreferences['bubbleTailStyle']>

type Resolved = {
	appearance: Required<AppearancePreferences>
	account: Required<AccountPreferences>
	ai: Required<AIPreferences>
	notifications: Required<NotificationPreferences>
	privacy: Required<PrivacyPreferences>
	accessibility: Required<AccessibilityPreferences>
}

const STORAGE_KEY = 'user-preferences:'

// ────────────────────────────────────────────────────────────
// local storage helpers
// ────────────────────────────────────────────────────────────

function readStorage(userId: string): UserPreferences {
	if (!browser) return {}
	try {
		const raw = localStorage.getItem(`${STORAGE_KEY}${userId}`)
		if (!raw) return {}
		const parsed = JSON.parse(raw)
		return isPlainObject(parsed) ? (parsed as UserPreferences) : {}
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
	const defaults: Resolved = $derived({
		appearance: {
			themeMode: (settingsState.data?.ui?.default_theme as ThemeMode) ?? 'system',
			accent: 'purple',
			background:
				(settingsState.data?.ui?.default_background as BackgroundType) ?? 'lightrays',
			autoAccentColors: true,
			autoBackground: true,
			staticColor: '#171717',
			bubbleTailStyle: 'none',
		},
		account: {
			bio: null,
			birthDate: null,
			gender: null,
		},
		ai: {
			defaultAgentId: settingsState.data?.ai?.default_agent_id ?? null,
			bio: null,
			useAccountBio: false,
			memoriesEnabled: true,
			chatRecall: true,
			customInstructions: null,
			personality: null,
		},
		notifications: {
			enabled: true,
			sound: true,
		},
		privacy: {
			saveHistory: true,
			shareUsageData: false,
			useLocation: false,
			useDeviceContext: true,
		},
		accessibility: {
			hapticFeedback: true,
			svgLiquidGlass: true,
		},
	})

	// user preferences → defaults (which already include admin settings)
	const data: Resolved = $derived(deepMerge(structuredClone(defaults), raw as Partial<Resolved>))
	const useSvgLiquidGlass = $derived.by(
		() => device.isChromium && (data.accessibility.svgLiquidGlass ?? true)
	)

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

	async function update<K extends keyof Resolved>(
		section: K,
		updates: Partial<Resolved[K]>
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
		get useSvgLiquidGlass() {
			return useSvgLiquidGlass
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
