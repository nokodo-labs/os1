import { browser } from '$app/environment'
import { v1Client } from '$lib/api/v1/client'
import { session } from '$lib/stores/session.svelte'

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

function readStored(userId: string): Preferences {
	if (!browser) return {}
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${userId}`)
		if (!raw) return {}
		return normalizePreferences(JSON.parse(raw) as unknown)
	} catch {
		return {}
	}
}

function writeStored(userId: string, prefs: Preferences): void {
	if (!browser) return
	try {
		window.localStorage.setItem(`${STORAGE_PREFIX}${userId}`, JSON.stringify(prefs))
	} catch {
		// ignore
	}
}

class PreferencesStore {
	data = $state<Preferences>({})
	loading = $state(false)
	error = $state<string | null>(null)

	#lastUserId: string | null = null

	startSync = (): (() => void) => {
		// Hydrate on start and whenever user changes
		const user = session.currentUser
		if (user && this.#lastUserId !== user.id) {
			this.#lastUserId = user.id
			this.data = readStored(user.id)
			void this.refresh()
		} else if (!user) {
			this.#lastUserId = null
			this.data = {}
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
			const { data, error } = await v1Client().GET('/users/{user_id}', {
				params: { path: { user_id: user.id } },
			})
			if (error || !data) {
				this.error = 'could not load preferences'
				return
			}
			const next = normalizePreferences(data.preferences)
			this.data = next
			session.currentUser = { ...data }
			writeStored(user.id, next)
		} finally {
			this.loading = false
		}
	}

	save = async (next: Preferences): Promise<boolean> => {
		const user = session.currentUser
		if (!user) return false
		this.error = null
		this.data = next
		writeStored(user.id, next)
		session.currentUser = user ? { ...user, preferences: next } : null

		const { data, error } = await v1Client().PATCH('/users/{user_id}', {
			params: { path: { user_id: user.id } },
			body: { preferences: next },
		})

		if (error || !data) {
			this.error = 'could not save preferences'
			return false
		}

		const normalized = normalizePreferences(data.preferences)
		this.data = normalized
		session.currentUser = { ...data, preferences: normalized }
		writeStored(user.id, normalized)
		return true
	}

	set = async (key: string, value: JsonValue): Promise<boolean> => {
		const next = { ...this.data, [key]: value }
		return await this.save(next)
	}

	hydrateFromUser = (user: { id: string; preferences?: unknown } | null): void => {
		if (!user) {
			this.data = {}
			this.loading = false
			this.error = null
			return
		}
		this.data = readStored(user.id)
		if (user.preferences) {
			const next = normalizePreferences(user.preferences)
			this.data = next
			writeStored(user.id, next)
		}
	}
}

export const preferences = new PreferencesStore()
