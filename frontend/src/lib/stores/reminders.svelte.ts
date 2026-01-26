/**
 * reminders store - caches lists, default counts, and reminders per list.
 * pattern follows chat.svelte.ts for consistency.
 *
 * cache strategy:
 * - generous TTL (30 min) with automatic refresh on API calls
 * - websocket events update cache in real-time
 * - stale data is still displayed (no loading state) while fetching
 * - if fetch fails, cache is cleared to force fresh load on next attempt
 * - trust cache by default since websocket keeps it up to date
 */

import { browser } from '$app/environment'
import { apiClient } from '$lib/api/client'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
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

// cache TTL - generous since websocket keeps cache fresh
const CACHE_TTL_MS = 30 * 60 * 1000 // 30 minutes

// reminder event types
const REMINDER_EVENT_TYPES = [
	'reminder.created',
	'reminder.updated',
	'reminder.completed',
	'reminder.deleted',
]
const REMINDER_LIST_EVENT_TYPES = [
	'reminder_list.created',
	'reminder_list.updated',
	'reminder_list.deleted',
]

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

	/** event stream subscription cleanup */
	#unsubscribe: (() => void) | null = null

	/** state: last visited list id for navigation continuity */
	lastVisitedListId = $state<string | null>(null)

	/** state: last visited reminders pathname for navigation continuity */
	lastVisitedPath = $state<string | null>(null)

	// ─────────────────────────────────────────────────────────────────────────
	// event stream integration
	// ─────────────────────────────────────────────────────────────────────────

	/**
	 * initialize event stream subscription for real-time updates.
	 */
	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
	}

	/**
	 * cleanup event stream subscription.
	 */
	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	/**
	 * handle incoming stream events for reminders.
	 */
	#handleStreamEvent = (message: StreamMessage): void => {
		const eventType = message.type

		// handle reminder events
		if (REMINDER_EVENT_TYPES.includes(eventType)) {
			const data = message.data as Record<string, unknown> | undefined
			if (!data) return

			if (eventType === 'reminder.created' || eventType === 'reminder.updated') {
				// upsert reminder in the appropriate list cache
				const reminder = data as unknown as ReminderWithSubtasks
				if (!reminder.id) return
				const listKey = this.#listKey(reminder.list_id ?? null)
				const entry = this.#remindersCache.get(listKey)
				if (entry) {
					const existing = entry.reminders.findIndex((r) => r.id === reminder.id)
					if (existing >= 0) {
						entry.reminders[existing] = reminder
					} else {
						entry.reminders = [...entry.reminders, reminder]
					}
					this.#remindersCache.set(listKey, { ...entry })
				}
				// update default counts if this is default list
				if (reminder.list_id === null || reminder.list_id === undefined) {
					this.#recalculateDefaultCounts()
				}
			} else if (eventType === 'reminder.completed') {
				// update status in cache
				const reminderId = data.reminder_id as string | undefined
				const completedAt = data.completed_at as string | undefined
				if (!reminderId) return
				this.#updateReminderInAllCaches(reminderId, (r) => ({
					...r,
					status: 'completed' as const,
					completed_at: completedAt ?? new Date().toISOString(),
				}))
				this.#recalculateDefaultCounts()
			} else if (eventType === 'reminder.deleted') {
				// remove from cache
				const reminderId = data.reminder_id as string | undefined
				if (!reminderId) return
				this.#removeReminderFromAllCaches(reminderId)
				this.#recalculateDefaultCounts()
			}
		}

		// handle reminder list events
		if (REMINDER_LIST_EVENT_TYPES.includes(eventType)) {
			const data = message.data as Record<string, unknown> | undefined
			if (!data) return

			if (eventType === 'reminder_list.created' || eventType === 'reminder_list.updated') {
				// upsert list in cache
				const list = data as unknown as ReminderListWithCounts
				if (!list.id) return
				if (this.#listsCache) {
					const existing = this.#listsCache.lists.findIndex((l) => l.id === list.id)
					if (existing >= 0) {
						this.#listsCache.lists[existing] = toListWithCounts(list)
					} else {
						this.#listsCache = {
							lists: [...this.#listsCache.lists, toListWithCounts(list)],
							fetchedAt: this.#listsCache.fetchedAt,
						}
					}
				}
			} else if (eventType === 'reminder_list.deleted') {
				// remove list from cache
				const listId = data.list_id as string | undefined
				if (!listId) return
				if (this.#listsCache) {
					this.#listsCache = {
						lists: this.#listsCache.lists.filter((l) => l.id !== listId),
						fetchedAt: this.#listsCache.fetchedAt,
					}
				}
				// also clear reminders cache for this list
				this.#remindersCache.delete(listId)
			}
		}
	}

	/**
	 * update a reminder across all list caches.
	 */
	#updateReminderInAllCaches(
		reminderId: string,
		updater: (r: ReminderWithSubtasks) => ReminderWithSubtasks
	): void {
		for (const [key, entry] of this.#remindersCache) {
			const idx = entry.reminders.findIndex((r) => r.id === reminderId)
			if (idx >= 0) {
				entry.reminders[idx] = updater(entry.reminders[idx])
				this.#remindersCache.set(key, { ...entry })
			}
		}
	}

	/**
	 * remove a reminder from all list caches.
	 */
	#removeReminderFromAllCaches(reminderId: string): void {
		for (const [key, entry] of this.#remindersCache) {
			const filtered = entry.reminders.filter((r) => r.id !== reminderId)
			if (filtered.length !== entry.reminders.length) {
				this.#remindersCache.set(key, { reminders: filtered, fetchedAt: entry.fetchedAt })
			}
		}
	}

	/**
	 * recalculate default counts from cached reminders.
	 */
	#recalculateDefaultCounts(): void {
		const defaultEntry = this.#remindersCache.get('default')
		if (defaultEntry) {
			const reminders = defaultEntry.reminders
			this.#defaultCountsCache = {
				counts: {
					total_count: reminders.length,
					pending_count: reminders.filter((r) => r.status === 'pending').length,
					completed_count: reminders.filter((r) => r.status === 'completed').length,
				},
				fetchedAt: Date.now(),
			}
		}
	}

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
	 * create a new reminder list.
	 * optimistically adds to cached lists (when present), then persists.
	 */
	async createList(params: {
		name: string
		icon?: string | null
		color?: string | null
	}): Promise<ReminderListWithCounts | null> {
		const { data, error } = await apiClient().POST('/v1/reminders/lists', {
			body: {
				name: params.name,
				icon: params.icon ?? null,
				color: params.color ?? null,
				position: 0,
			},
		})

		if (error || !data) return null

		const created = toListWithCounts(data as ReminderListWithCounts)

		if (this.#listsCache) {
			this.#listsCache = {
				lists: [...this.#listsCache.lists, created],
				fetchedAt: this.#listsCache.fetchedAt,
			}
		} else {
			this.invalidateLists()
		}

		this.lastVisitedListId = created.id
		this.lastVisitedPath = `/reminders/lists/${created.id}`
		return created
	}

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
				reminders: [...existing.reminders, reminder],
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
		const previous = this.#findReminderInCache(reminder.list_id, reminder.id) ?? reminder
		this.#updateReminderInCache(reminder.list_id, {
			...previous,
			status: 'completed',
		})

		const { data, error } = await apiClient().POST('/v1/reminders/{reminder_id}/complete', {
			params: { path: { reminder_id: reminder.id } },
		})

		if (error || !data) {
			this.#updateReminderInCache(reminder.list_id, previous)
			return null
		}

		const updated: ReminderWithSubtasks = {
			...previous,
			...data,
			status: 'completed',
			subtasks: previous.subtasks,
		}
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
		const previous = this.#findReminderInCache(reminder.list_id, reminder.id) ?? reminder
		this.#updateReminderInCache(reminder.list_id, {
			...previous,
			status: 'pending',
		})

		const { data, error } = await apiClient().PATCH('/v1/reminders/{reminder_id}', {
			params: { path: { reminder_id: reminder.id } },
			body: { status: 'pending' },
		})

		if (error || !data) {
			this.#updateReminderInCache(reminder.list_id, previous)
			return null
		}

		const updated: ReminderWithSubtasks = {
			...previous,
			...data,
			status: 'pending',
			subtasks: previous.subtasks,
		}
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
	 * update a reminder's title/description.
	 */
	async updateReminder(
		reminder: ReminderWithSubtasks,
		updates: { title?: string; description?: string | null }
	): Promise<ReminderWithSubtasks | null> {
		const { data, error } = await apiClient().PATCH('/v1/reminders/{reminder_id}', {
			params: { path: { reminder_id: reminder.id } },
			body: updates,
		})

		if (error || !data) return null

		const updated: ReminderWithSubtasks = { ...reminder, ...data, subtasks: reminder.subtasks }
		this.#updateReminderInCache(reminder.list_id, updated)
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

	/**
	 * move a reminder to a different list.
	 */
	async moveReminder(
		reminder: ReminderWithSubtasks,
		targetListId: string | null
	): Promise<ReminderWithSubtasks | null> {
		const currentListId = reminder.list_id ?? null
		if (currentListId === targetListId) return reminder

		const previous = this.#findReminderInCache(currentListId, reminder.id) ?? reminder
		const optimistic: ReminderWithSubtasks = {
			...previous,
			list_id: targetListId,
		}

		this.#removeReminderFromCache(currentListId, reminder.id)
		this.#appendReminderToCache(targetListId, optimistic)

		const { data, error } = await apiClient().PATCH('/v1/reminders/{reminder_id}', {
			params: { path: { reminder_id: reminder.id } },
			body: { list_id: targetListId },
		})

		if (error || !data) {
			this.#removeReminderFromCache(targetListId, reminder.id)
			this.#appendReminderToCache(currentListId, previous)
			return null
		}

		const updated: ReminderWithSubtasks = {
			...optimistic,
			...data,
			list_id: targetListId,
			subtasks: previous.subtasks,
		}
		this.#updateReminderInCache(targetListId, updated)

		// invalidate counts
		if (currentListId === null || targetListId === null) {
			this.invalidateDefaultCounts()
		}
		this.invalidateLists()

		return updated
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

	#findReminderInCache(
		listId: string | null | undefined,
		reminderId: string
	): ReminderWithSubtasks | null {
		const key = this.#listKey(listId ?? null)
		const existing = this.#remindersCache.get(key)
		if (!existing) return null
		return existing.reminders.find((r) => r.id === reminderId) ?? null
	}

	#removeReminderFromCache(listId: string | null | undefined, reminderId: string): void {
		const key = this.#listKey(listId ?? null)
		const existing = this.#remindersCache.get(key)
		if (!existing) return
		this.#remindersCache.set(key, {
			reminders: existing.reminders.filter((r) => r.id !== reminderId),
			fetchedAt: existing.fetchedAt,
		})
	}

	#appendReminderToCache(
		listId: string | null | undefined,
		reminder: ReminderWithSubtasks
	): void {
		const key = this.#listKey(listId ?? null)
		const existing = this.#remindersCache.get(key)
		if (!existing) return
		this.#remindersCache.set(key, {
			reminders: [...existing.reminders, reminder],
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

// initialize event stream and handle auth changes
if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			reminders.init()
		} else {
			reminders.cleanup()
			reminders.clear()
		}
	})
}
