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

export type {
	AIPreferences,
	AppearancePreferences,
	NotificationPreferences,
	PrivacyPreferences,
	UserPreferences,
}

export type ThemeMode = NonNullable<AppearancePreferences['themeMode']>
export type AccentColor = NonNullable<AppearancePreferences['accent']>
export type BackgroundType = NonNullable<AppearancePreferences['background']>

const DEFAULT_THEME_MODE: ThemeMode = 'system'
const DEFAULT_ACCENT: AccentColor = 'purple'
const DEFAULT_BACKGROUND: BackgroundType = 'darkveil'

const STORAGE_PREFIX = 'user-preferences:'

function isPlainObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizePreferences(value: unknown): UserPreferences {
	// backend validates shape; on the client we only need to ensure we don't
	// hydrate from non-objects (e.g., corrupted localStorage)
	if (!isPlainObject(value)) return {}
	return value as UserPreferences
}

function readStored(userId: string): UserPreferences {
	if (!browser) return {}
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${userId}`)
		if (!raw) return {}
		return normalizePreferences(JSON.parse(raw) as unknown)
	} catch {
		return {}
	}
}

function writeStored(userId: string, prefs: UserPreferences): void {
	if (!browser) return
	try {
		window.localStorage.setItem(`${STORAGE_PREFIX}${userId}`, JSON.stringify(prefs))
	} catch {
		// ignore
	}
}

class PreferencesStore {
	#data = $state<UserPreferences>({})
	loading = $state(false)
	error = $state<string | null>(null)

	#lastUserId: string | null = null

	get data() {
		return this.#data
	}

	// ------------------------------------------------------------
	// derived getters (with settings fallback)
	// ------------------------------------------------------------

	get themeMode(): ThemeMode {
		const pref = this.#data.appearance?.themeMode
		if (pref) return pref
		const settingsDefault = settingsState.data?.ui?.default_theme
		if (
			settingsDefault === 'light' ||
			settingsDefault === 'dark' ||
			settingsDefault === 'system'
		) {
			return settingsDefault
		}
		return DEFAULT_THEME_MODE
	}

	get accent(): AccentColor {
		return this.#data.appearance?.accent ?? DEFAULT_ACCENT
	}

	get background(): BackgroundType {
		return this.#data.appearance?.background ?? DEFAULT_BACKGROUND
	}

	get defaultAgentId(): string | null {
		const pref = this.#data.ai?.defaultAgentId
		if (pref) return pref
		return settingsState.data?.ai?.default_agent_id ?? null
	}

	get notificationsEnabled(): boolean {
		return this.#data.notifications?.enabled ?? true
	}

	get notificationSound(): boolean {
		return this.#data.notifications?.sound ?? true
	}

	get saveHistory(): boolean {
		return this.#data.privacy?.saveHistory ?? true
	}

	get shareUsageData(): boolean {
		return this.#data.privacy?.shareUsageData ?? false
	}

	startSync = (): (() => void) => {
		// Hydrate on start and whenever user changes
		const user = session.currentUser
		if (user && this.#lastUserId !== user.id) {
			this.#lastUserId = user.id
			this.#data = readStored(user.id)
			void this.refresh()
		} else if (!user) {
			this.#lastUserId = null
			this.#data = {}
			this.loading = false
			this.error = null
		}
		return () => {
			// cleanup if needed
		}
	}

	refresh = async (): Promise<void> => {
		const user = session.currentUser
		if (!user) return
		this.loading = true
		this.error = null
		try {
			const { data, error } = await apiClient().GET('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
			})
			if (error || !data) {
				this.error = 'could not load preferences'
				return
			}
			const next = (data.preferences ?? {}) as UserPreferences
			this.#data = next
			session.currentUser = { ...data }
			writeStored(user.id, next)
		} finally {
			this.loading = false
		}
	}

	setAppearance = async (updates: Partial<AppearancePreferences>): Promise<boolean> => {
		const next: UserPreferences = {
			...this.#data,
			appearance: { ...this.#data.appearance, ...updates },
		}
		return await this.#save(next)
	}

	setAI = async (updates: Partial<AIPreferences>): Promise<boolean> => {
		const next: UserPreferences = {
			...this.#data,
			ai: { ...this.#data.ai, ...updates },
		}
		return await this.#save(next)
	}

	setNotifications = async (updates: Partial<NotificationPreferences>): Promise<boolean> => {
		const next: UserPreferences = {
			...this.#data,
			notifications: { ...this.#data.notifications, ...updates },
		}
		return await this.#save(next)
	}

	setPrivacy = async (updates: Partial<PrivacyPreferences>): Promise<boolean> => {
		const next: UserPreferences = {
			...this.#data,
			privacy: { ...this.#data.privacy, ...updates },
		}
		return await this.#save(next)
	}

	#save = async (next: UserPreferences): Promise<boolean> => {
		const user = session.currentUser
		if (!user) return false
		this.error = null
		this.#data = next
		writeStored(user.id, next)
		session.currentUser = { ...user, preferences: next }

		const { data, error } = await apiClient().PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: user.id } },
			body: { preferences: next },
		})

		if (error || !data) {
			this.error = 'could not save preferences'
			return false
		}

		const saved = (data.preferences ?? {}) as UserPreferences
		this.#data = saved
		session.currentUser = { ...data, preferences: saved }
		writeStored(user.id, saved)
		return true
	}

	set(key: 'appearance.themeMode', value: ThemeMode): Promise<boolean>
	set(key: 'appearance.accent', value: AccentColor): Promise<boolean>
	set(key: 'appearance.background', value: AppearancePreferences['background']): Promise<boolean>
	set(key: string, value: unknown): Promise<boolean>
	async set(key: string, value: unknown): Promise<boolean> {
		// compat shim for the old "dot key" style.
		// only keep the keys that are used in-app.
		switch (key) {
			case 'appearance.themeMode': {
				if (value === 'light' || value === 'dark' || value === 'system') {
					return await this.setAppearance({ themeMode: value })
				}
				return false
			}
			case 'appearance.accent': {
				if (typeof value === 'string') {
					return await this.setAppearance({ accent: value as AccentColor })
				}
				return false
			}
			case 'appearance.background': {
				if (typeof value === 'string' || value === null) {
					return await this.setAppearance({
						background: value as AppearancePreferences['background'],
					})
				}
				return false
			}
			default:
				return false
		}
	}

	hydrateFromUser = (user: { id: string; preferences?: UserPreferences | null } | null): void => {
		if (!user) {
			this.#data = {}
			this.loading = false
			this.error = null
			return
		}
		this.#data = readStored(user.id)
		if (user.preferences) {
			this.#data = user.preferences
			writeStored(user.id, user.preferences)
		}
	}
}

export const preferences = new PreferencesStore()
