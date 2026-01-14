import { v1Client } from '$lib/api/v1/client'
import { currentUser } from '$lib/stores/session'
import { get, writable } from 'svelte/store'

export type JsonValue =
	| string
	| number
	| boolean
	| null
	| JsonValue[]
	| { [key: string]: JsonValue }

export type Preferences = Record<string, JsonValue>

/**
 * client-side persistence namespace for this store.
 *
 * prefixing by feature keeps keys grouped and avoids collisions.
 */
const STORAGE_PREFIX = 'user-preferences:'

function isPlainObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isJsonValue(value: unknown, depth = 0): value is JsonValue {
	if (depth > 20) return false
	if (value === null) return true
	if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
		return true
	if (Array.isArray(value)) return value.every((v) => isJsonValue(v, depth + 1))
	if (isPlainObject(value)) return Object.values(value).every((v) => isJsonValue(v, depth + 1))
	return false
}

function normalizePreferences(value: unknown): Preferences {
	if (!isPlainObject(value)) return {}
	const out: Preferences = {}
	for (const [key, v] of Object.entries(value)) {
		if (isJsonValue(v)) out[key] = v
	}
	return out
}

function readStoredPreferences(userId: string): Preferences {
	if (typeof window === 'undefined') return {}
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${userId}`)
		if (!raw) return {}
		return normalizePreferences(JSON.parse(raw) as unknown)
	} catch {
		return {}
	}
}

function writeStoredPreferences(userId: string, prefs: Preferences): void {
	if (typeof window === 'undefined') return
	try {
		window.localStorage.setItem(`${STORAGE_PREFIX}${userId}`, JSON.stringify(prefs))
	} catch {
		// ignore
	}
}

export const preferences = writable<Preferences>({})
export const preferencesLoading = writable(false)
export const preferencesError = writable<string | null>(null)

let lastUserId: string | null = null
let didHydrateFromStorage = false

/**
 * keeps the `preferences` store in sync with the authenticated user.
 *
 * behavior:
 * - when the user changes (login/logout/switch), reset and hydrate from localstorage
 * - refresh from the api once per user session to reconcile with server state
 * - if `currentUser.preferences` changes elsewhere, mirror it into this store + localstorage
 */
export function startPreferencesSync(): () => void {
	const unsubscribe = currentUser.subscribe((user) => {
		const userId = user?.id ?? null
		if (!userId) {
			lastUserId = null
			didHydrateFromStorage = false
			preferences.set({})
			preferencesLoading.set(false)
			preferencesError.set(null)
			return
		}

		if (!user) return

		if (lastUserId !== userId) {
			lastUserId = userId
			didHydrateFromStorage = false
		}

		if (!didHydrateFromStorage) {
			didHydrateFromStorage = true
			preferences.set(readStoredPreferences(userId))
			void refreshPreferences()
			return
		}

		if (user.preferences) {
			const next = normalizePreferences(user.preferences)
			preferences.set(next)
			writeStoredPreferences(userId, next)
		}
	})

	return unsubscribe
}

/** fetch latest preferences for the current user from the api. */
export async function refreshPreferences(): Promise<void> {
	const user = get(currentUser)
	if (!user) return
	preferencesLoading.set(true)
	preferencesError.set(null)
	try {
		const { data, error } = await v1Client().GET('/users/{user_id}', {
			params: { path: { user_id: user.id } },
		})
		if (error || !data) {
			preferencesError.set('could not load preferences')
			return
		}
		const next = normalizePreferences(data.preferences)
		preferences.set(next)
		currentUser.set({ ...data })
		writeStoredPreferences(user.id, next)
	} finally {
		preferencesLoading.set(false)
	}
}

/**
 * optimistic local update + server persistence via `PATCH /users/{user_id}`.
 * returns `true` when the server accepts the update.
 */
export async function savePreferences(next: Preferences): Promise<boolean> {
	const user = get(currentUser)
	if (!user) return false
	preferencesError.set(null)
	preferences.set(next)
	writeStoredPreferences(user.id, next)
	currentUser.update((u) => (u ? { ...u, preferences: next } : u))

	const { data, error } = await v1Client().PATCH('/users/{user_id}', {
		params: { path: { user_id: user.id } },
		body: { preferences: next },
	})

	if (error || !data) {
		preferencesError.set('could not save preferences')
		return false
	}

	const normalized = normalizePreferences(data.preferences)
	preferences.set(normalized)
	currentUser.set({ ...data, preferences: normalized })
	writeStoredPreferences(user.id, normalized)
	return true
}

/** convenience helper for updating a single preference key. */
export async function setPreference(key: string, value: JsonValue): Promise<boolean> {
	const current = get(preferences)
	const next = { ...current, [key]: value }
	return await savePreferences(next)
}
