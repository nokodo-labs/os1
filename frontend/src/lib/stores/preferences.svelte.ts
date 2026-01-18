import { browser } from '$app/environment'
import { v1Client } from '$lib/api/v1/client'
import { currentUser, setCurrentUser, updateCurrentUser } from '$lib/stores/session.svelte'

export type JsonValue =
	| string
	| number
	| boolean
	| null
	| JsonValue[]
	| { [key: string]: JsonValue }

export type Preferences = Record<string, JsonValue>

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
	if (!browser) return {}
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${userId}`)
		if (!raw) return {}
		return normalizePreferences(JSON.parse(raw) as unknown)
	} catch {
		return {}
	}
}

function writeStoredPreferences(userId: string, prefs: Preferences): void {
	if (!browser) return
	try {
		window.localStorage.setItem(`${STORAGE_PREFIX}${userId}`, JSON.stringify(prefs))
	} catch {
		// ignore
	}
}

export let preferences = $state<Preferences>({})
export let preferencesLoading = $state(false)
export let preferencesError = $state<string | null>(null)

let lastUserId: string | null = null
let didHydrateFromStorage = false

let preferencesSyncEnabled = $state(false)

$effect(() => {
	if (!preferencesSyncEnabled) return
	const user = currentUser
	const userId = user?.id ?? null
	if (!userId) {
		lastUserId = null
		didHydrateFromStorage = false
		preferences = {}
		preferencesLoading = false
		preferencesError = null
		return
	}

	if (lastUserId !== userId) {
		lastUserId = userId
		didHydrateFromStorage = false
	}

	if (!didHydrateFromStorage) {
		didHydrateFromStorage = true
		preferences = readStoredPreferences(userId)
		void refreshPreferences()
		return
	}

	if (user?.preferences) {
		const next = normalizePreferences(user.preferences)
		preferences = next
		writeStoredPreferences(userId, next)
	}
})

export function startPreferencesSync(): () => void {
	preferencesSyncEnabled = true
	return () => {
		preferencesSyncEnabled = false
	}
}

export async function refreshPreferences(): Promise<void> {
	const user = currentUser
	if (!user) return
	preferencesLoading = true
	preferencesError = null
	try {
		const { data, error } = await v1Client().GET('/users/{user_id}', {
			params: { path: { user_id: user.id } },
		})
		if (error || !data) {
			preferencesError = 'could not load preferences'
			return
		}
		const next = normalizePreferences(data.preferences)
		preferences = next
		setCurrentUser({ ...data })
		writeStoredPreferences(user.id, next)
	} finally {
		preferencesLoading = false
	}
}

export async function savePreferences(next: Preferences): Promise<boolean> {
	const user = currentUser
	if (!user) return false
	preferencesError = null
	preferences = next
	writeStoredPreferences(user.id, next)
	updateCurrentUser((u) => (u ? { ...u, preferences: next } : u))

	const { data, error } = await v1Client().PATCH('/users/{user_id}', {
		params: { path: { user_id: user.id } },
		body: { preferences: next },
	})

	if (error || !data) {
		preferencesError = 'could not save preferences'
		return false
	}

	const normalized = normalizePreferences(data.preferences)
	preferences = normalized
	setCurrentUser({ ...data, preferences: normalized })
	writeStoredPreferences(user.id, normalized)
	return true
}

export async function setPreference(key: string, value: JsonValue): Promise<boolean> {
	const current = preferences
	const next = { ...current, [key]: value }
	return await savePreferences(next)
}
