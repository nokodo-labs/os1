/**
 * reminders store - caches lists, default counts, and reminders per list.
 * pattern follows chat.svelte.ts for consistency.
 */

import { browser } from '$app/environment'
import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { onAccessTokenChanged } from '$lib/auth/session.svelte'
import { SvelteMap } from 'svelte/reactivity'

// types from API
export type Reminder = components['schemas']['Reminder']
export type ReminderWithSubtasks = components['schemas']['ReminderWithSubtasks']
export type ReminderList = components['schemas']['ReminderList']
export type ReminderListWithCounts = components['schemas']['ReminderListWithCounts']

export type Counts = {
	total_count: number
	pending_count: number
	completed_count: number
}

// cache TTL in milliseconds
const CACHE_TTL_MS = 2 * 60 * 1000 // 2 minutes

interface ListsCacheEntry {
	lists: ReminderListWithCounts[]
	fetchedAt: number
}

interface DefaultCountsCacheEntry {
	counts: Counts
	fetchedAt: number
}

interface RemindersCacheEntry {
	reminders: ReminderWithSubtasks[]
	fetchedAt: number
}

// ─────────────────────────────────────────────────────────────────────────────
// reminders cache
// ─────────────────────────────────────────────────────────────────────────────

class RemindersCache {
	/** lists with counts */
	#listsCache = $state<ListsCacheEntry | null>(null)

	/** default list (null list_id) counts */
	#defaultCountsCache = $state<DefaultCountsCacheEntry | null>(null)

	/** reminders per list (key: list_id or 'default' for null) */
	readonly #remindersCache = new SvelteMap<string, RemindersCacheEntry>()

	/** in-flight fetch promises to dedupe concurrent requests */
	#listsInFlight: Promise<ReminderListWithCounts[]> | null = null
	#defaultCountsInFlight: Promise<Counts> | null = null
	readonly #remindersInFlight = new SvelteMap<string, Promise<ReminderWithSubtasks[]>>()

	/** state: last visited list id for navigation continuity */
	lastVisitedListId = $state<string | null>(null)

	/** state: last visited reminders pathname for navigation continuity */
	lastVisitedPath = $state<string | null>(null)

	get remindersAppUrl(): string {
		const path = this.lastVisitedPath
		if (path && (path === '/reminders' || path.startsWith('/reminders/lists/'))) {
			return path
		}

		const listId = this.lastVisitedListId
		return listId ? `/reminders/lists/${listId}` : '/reminders'
	}

	#isFresh(fetchedAt: number): boolean {
		return Date.now() - fetchedAt < CACHE_TTL_MS
	}

	#listKey(listId: string | null): string {
		return listId ?? 'default'
	}

	// ─────────────────────────────────────────────────────────────────────────
	// lists
	// ─────────────────────────────────────────────────────────────────────────

	get lists(): ReminderListWithCounts[] {
		return this.#listsCache?.lists ?? []
	}

	get isListsFresh(): boolean {
		return this.#listsCache !== null && this.#isFresh(this.#listsCache.fetchedAt)
	}

	setLists(lists: ReminderListWithCounts[]): void {
		this.#listsCache = { lists, fetchedAt: Date.now() }
	}

	async loadLists(options?: { force?: boolean }): Promise<ReminderListWithCounts[]> {
		const force = options?.force ?? false

		if (!force && this.isListsFresh) {
			return this.lists
		}

		if (this.#listsInFlight) return this.#listsInFlight

		this.#listsInFlight = (async () => {
			const { data, error } = await apiClient().GET('/v1/reminders/lists', {
				params: { query: { include_counts: true } },
			})
			if (error || !data) return this.lists
			const lists = data.map(toListWithCounts)
			this.setLists(lists)
			return lists
		})()

		try {
			return await this.#listsInFlight
		} finally {
			this.#listsInFlight = null
		}
	}

	invalidateLists(): void {
		this.#listsCache = null
	}

	// ─────────────────────────────────────────────────────────────────────────
	// default counts (computed from default list reminders)
	// ─────────────────────────────────────────────────────────────────────────

	get defaultCounts(): Counts {
		return (
			this.#defaultCountsCache?.counts ?? {
				total_count: 0,
				pending_count: 0,
				completed_count: 0,
			}
		)
	}

	get isDefaultCountsFresh(): boolean {
		return (
			this.#defaultCountsCache !== null && this.#isFresh(this.#defaultCountsCache.fetchedAt)
		)
	}

	setDefaultCounts(counts: Counts): void {
		this.#defaultCountsCache = { counts, fetchedAt: Date.now() }
	}

	/**
	 * load default list counts by fetching all default reminders and counting them.
	 * this is derived from the reminders themselves since there's no dedicated counts endpoint.
	 */
	async loadDefaultCounts(options?: { force?: boolean }): Promise<Counts> {
		const force = options?.force ?? false

		if (!force && this.isDefaultCountsFresh) {
			return this.defaultCounts
		}

		if (this.#defaultCountsInFlight) return this.#defaultCountsInFlight

		this.#defaultCountsInFlight = (async () => {
			// load default list reminders to compute counts
			const reminders = await this.loadReminders(null, { force })
			const counts: Counts = {
				total_count: reminders.length,
				pending_count: reminders.filter((r) => r.status === 'pending').length,
				completed_count: reminders.filter((r) => r.status === 'completed').length,
			}
			this.setDefaultCounts(counts)
			return counts
		})()

		try {
			return await this.#defaultCountsInFlight
		} finally {
			this.#defaultCountsInFlight = null
		}
	}

	invalidateDefaultCounts(): void {
		this.#defaultCountsCache = null
	}

	// ─────────────────────────────────────────────────────────────────────────
	// reminders (per list)
	// ─────────────────────────────────────────────────────────────────────────

	getReminders(listId: string | null): ReminderWithSubtasks[] {
		const key = this.#listKey(listId)
		return this.#remindersCache.get(key)?.reminders ?? []
	}

	isRemindersFresh(listId: string | null): boolean {
		const key = this.#listKey(listId)
		const entry = this.#remindersCache.get(key)
		return entry !== null && entry !== undefined && this.#isFresh(entry.fetchedAt)
	}

	setReminders(listId: string | null, reminders: ReminderWithSubtasks[]): void {
		const key = this.#listKey(listId)
		this.#remindersCache.set(key, { reminders, fetchedAt: Date.now() })
	}

	async loadReminders(
		listId: string | null,
		options?: { force?: boolean }
	): Promise<ReminderWithSubtasks[]> {
		const force = options?.force ?? false
		const key = this.#listKey(listId)

		if (!force && this.isRemindersFresh(listId)) {
			return this.getReminders(listId)
		}

		const existing = this.#remindersInFlight.get(key)
		if (existing) return existing

		const promise = (async () => {
			const query: { list_id?: string | null; include_subtasks?: boolean } = {
				include_subtasks: true,
			}
			if (listId !== null) query.list_id = listId

			const { data, error } = await apiClient().GET('/v1/reminders', {
				params: { query },
			})
			if (error || !data) return this.getReminders(listId)
			const reminders = data as ReminderWithSubtasks[]
			this.setReminders(listId, reminders)
			return reminders
		})()

		this.#remindersInFlight.set(key, promise)
		try {
			return await promise
		} finally {
			this.#remindersInFlight.delete(key)
		}
	}

	invalidateReminders(listId: string | null): void {
		const key = this.#listKey(listId)
		this.#remindersCache.delete(key)
	}

	// ─────────────────────────────────────────────────────────────────────────
	// mutations
	// ─────────────────────────────────────────────────────────────────────────

	/**
	 * create a new reminder.
	 * optimistically adds to cache, then persists.
	 */
	async createReminder(params: {
		title: string
		listId: string | null
		description?: string | null
	}): Promise<ReminderWithSubtasks | null> {
		const { data, error } = await apiClient().POST('/v1/reminders', {
			body: {
				title: params.title,
				list_id: params.listId,
				description: params.description,
				status: 'pending',
				position: 0,
			},
		})

		if (error || !data) return null

		const reminder: ReminderWithSubtasks = { ...data, subtasks: [] }

		// update cache
		const key = this.#listKey(params.listId)
		const existing = this.#remindersCache.get(key)
		if (existing) {
			this.#remindersCache.set(key, {
				reminders: [reminder, ...existing.reminders],
				fetchedAt: existing.fetchedAt,
			})
		}

		// invalidate counts
		if (params.listId === null) {
			this.invalidateDefaultCounts()
		} else {
			this.invalidateLists() // list counts may change
		}

		return reminder
	}

	/**
	 * complete a reminder.
	 */
	async completeReminder(reminder: ReminderWithSubtasks): Promise<ReminderWithSubtasks | null> {
		const { data, error } = await apiClient().POST('/v1/reminders/{reminder_id}/complete', {
			params: { path: { reminder_id: reminder.id } },
		})

		if (error || !data) return null

		const updated: ReminderWithSubtasks = { ...reminder, ...data, subtasks: reminder.subtasks }
		this.#updateReminderInCache(reminder.list_id, updated)

		// invalidate counts
		if (reminder.list_id === null) {
			this.invalidateDefaultCounts()
		} else {
			this.invalidateLists()
		}

		return updated
	}

	/**
	 * uncomplete a reminder (set status back to pending).
	 */
	async uncompleteReminder(reminder: ReminderWithSubtasks): Promise<ReminderWithSubtasks | null> {
		const { data, error } = await apiClient().PATCH('/v1/reminders/{reminder_id}', {
			params: { path: { reminder_id: reminder.id } },
			body: { status: 'pending' },
		})

		if (error || !data) return null

		const updated: ReminderWithSubtasks = { ...reminder, ...data, subtasks: reminder.subtasks }
		this.#updateReminderInCache(reminder.list_id, updated)

		// invalidate counts
		if (reminder.list_id === null) {
			this.invalidateDefaultCounts()
		} else {
			this.invalidateLists()
		}

		return updated
	}

	/**
	 * delete a reminder.
	 */
	async deleteReminder(reminder: ReminderWithSubtasks): Promise<boolean> {
		const { error } = await apiClient().DELETE('/v1/reminders/{reminder_id}', {
			params: { path: { reminder_id: reminder.id } },
		})

		if (error) return false

		// remove from cache
		const key = this.#listKey(reminder.list_id ?? null)
		const existing = this.#remindersCache.get(key)
		if (existing) {
			this.#remindersCache.set(key, {
				reminders: existing.reminders.filter((r) => r.id !== reminder.id),
				fetchedAt: existing.fetchedAt,
			})
		}

		// invalidate counts
		if (reminder.list_id === null) {
			this.invalidateDefaultCounts()
		} else {
			this.invalidateLists()
		}

		return true
	}

	#updateReminderInCache(listId: string | null | undefined, updated: ReminderWithSubtasks): void {
		const key = this.#listKey(listId ?? null)
		const existing = this.#remindersCache.get(key)
		if (!existing) return

		this.#remindersCache.set(key, {
			reminders: existing.reminders.map((r) => (r.id === updated.id ? updated : r)),
			fetchedAt: existing.fetchedAt,
		})
	}

	// ─────────────────────────────────────────────────────────────────────────
	// global
	// ─────────────────────────────────────────────────────────────────────────

	/**
	 * load both lists and default counts in parallel.
	 */
	async loadListsAndCounts(options?: { force?: boolean }): Promise<void> {
		await Promise.all([this.loadLists(options), this.loadDefaultCounts(options)])
	}

	/**
	 * invalidate all caches.
	 */
	invalidateAll(): void {
		this.#listsCache = null
		this.#defaultCountsCache = null
		this.#remindersCache.clear()
	}

	/**
	 * clear all caches (e.g., on logout).
	 */
	clear(): void {
		this.invalidateAll()
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// helpers
// ─────────────────────────────────────────────────────────────────────────────

function toListWithCounts(list: ReminderListWithCounts | ReminderList): ReminderListWithCounts {
	if ('pending_count' in list) return list
	return { ...list, total_count: 0, pending_count: 0, completed_count: 0 }
}

// ─────────────────────────────────────────────────────────────────────────────
// singleton export
// ─────────────────────────────────────────────────────────────────────────────

export const reminders = new RemindersCache()

// clear on logout
if (browser) {
	onAccessTokenChanged((token) => {
		if (!token) reminders.clear()
	})
}
