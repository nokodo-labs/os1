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
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { showError } from '$lib/stores/notifications.svelte'
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

export type ListSortBy = 'position' | 'name' | 'created_at' | 'updated_at'
export type SortDir = 'asc' | 'desc'
export type ReminderListsSortMode = `${ListSortBy}:${SortDir}`

// cache TTL - generous since websocket keeps cache fresh
const CACHE_TTL_MS = 30 * 60 * 1000 // 30 minutes

interface ListsCacheEntry {
	/** id → list (preserves insertion order) */
	data: SvelteMap<string, ReminderListWithCounts>
	fetchedAt: number
}

function buildListsCache(lists: ReminderListWithCounts[], fetchedAt: number): ListsCacheEntry {
	const data = new SvelteMap<string, ReminderListWithCounts>()
	for (const list of lists) {
		data.set(list.id, list)
	}
	return { data, fetchedAt }
}

interface DefaultCountsCacheEntry {
	counts: Counts
	fetchedAt: number
}

interface RemindersCacheEntry {
	reminders: ReminderWithSubtasks[]
	fetchedAt: number
}

// reminders cache

class RemindersCache {
	/** lists with counts (id → list) */
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

	/** sort mode for reminder lists */
	listsSortMode = $state<ReminderListsSortMode>('position:asc')

	// event stream integration

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
	 * WS is the canonical source of truth: apply event data directly.
	 */
	#handleStreamEvent = (message: StreamMessage): void => {
		const data = message.data as Record<string, unknown> | undefined
		if (!data) return

		switch (message.type) {
			// ── reminder events ──
			case 'reminder.created': {
				const incoming = data as unknown as ReminderWithSubtasks
				if (!incoming?.id) return
				const listId = incoming.list_id ?? null
				const parentId = incoming.parent_id ?? null
				const key = this.#listKey(listId)
				const entry = this.#remindersCache.get(key)
				if (!entry) return

				if (parentId) {
					// subtask: add to parent's subtasks
					const parent = entry.reminders.find((r) => r.id === parentId)
					if (parent && !parent.subtasks?.some((s) => s.id === incoming.id)) {
						this.#updateReminderInCache(listId, {
							...parent,
							subtasks: [...(parent.subtasks ?? []), incoming],
						})
					}
				} else if (!entry.reminders.some((r) => r.id === incoming.id)) {
					// top-level: append (dedup against optimistic add)
					const withSubtasks = { ...incoming, subtasks: incoming.subtasks ?? [] }
					this.#remindersCache.set(key, {
						reminders: [...entry.reminders, withSubtasks],
						fetchedAt: entry.fetchedAt,
					})
				} else {
					// already exists (optimistic add): apply authoritative data
					this.#updateReminderInCache(listId, {
						...incoming,
						subtasks: incoming.subtasks ?? [],
					})
				}
				this.#recomputeCounts(listId)
				break
			}

			case 'reminder.updated':
			case 'reminder.completed': {
				const incoming = data as unknown as ReminderWithSubtasks & {
					previous_list_id?: string | null
					cascade?: boolean
				}
				if (!incoming?.id) return
				const listId = incoming.list_id ?? null
				const prevListId = incoming.previous_list_id ?? undefined

				// handle list move
				if (prevListId !== undefined && prevListId !== (incoming.list_id ?? null)) {
					if (prevListId !== null) {
						this.#removeReminderFromCache(prevListId, incoming.id)
						this.#recomputeCounts(prevListId)
					}
					const key = this.#listKey(listId)
					const entry = this.#remindersCache.get(key)
					if (entry && !entry.reminders.some((r) => r.id === incoming.id)) {
						const existing = this.#findReminderInCache(prevListId, incoming.id)
						this.#remindersCache.set(key, {
							reminders: [
								...entry.reminders,
								{
									...(existing ?? ({} as ReminderWithSubtasks)),
									...incoming,
									subtasks: existing?.subtasks ?? incoming.subtasks ?? [],
								},
							],
							fetchedAt: entry.fetchedAt,
						})
					}
				} else {
					// same list: merge partial update into existing cache entry
					const existing = this.#findReminderInCache(listId, incoming.id)
					if (existing) {
						this.#updateReminderInCache(listId, {
							...existing,
							...incoming,
							subtasks: existing.subtasks ?? incoming.subtasks ?? [],
						})
					}
				}

				// handle cascade completion
				if (incoming.cascade && message.type === 'reminder.completed') {
					const parent = this.#findReminderInCache(listId, incoming.id)
					if (parent?.subtasks?.length) {
						this.#updateReminderInCache(listId, {
							...parent,
							subtasks: parent.subtasks.map((s) =>
								s.status !== 'completed'
									? {
											...s,
											status: 'completed' as const,
											completed_at: incoming.completed_at ?? null,
										}
									: s
							),
						})
					}
				}

				this.#recomputeCounts(listId)
				break
			}

			case 'reminder.deleted': {
				const reminderId = data.id as string
				const listId = (data.list_id as string) ?? null
				if (!reminderId) return
				this.#removeReminderFromCache(listId, reminderId)
				this.#recomputeCounts(listId)
				break
			}

			// ── reminder list events ──
			case 'reminder_list.created': {
				const list = data as unknown as ReminderListWithCounts
				if (!list?.id || !this.#listsCache) return
				if (!this.#listsCache.data.has(list.id)) {
					this.#listsCache.data.set(list.id, {
						...list,
						total_count: 0,
						pending_count: 0,
						completed_count: 0,
					})
				}
				break
			}

			case 'reminder_list.updated': {
				const list = data as unknown as ReminderList
				if (!list?.id || !this.#listsCache) return
				const existing = this.#listsCache.data.get(list.id)
				if (existing) {
					// preserve counts, update other fields
					this.#listsCache.data.set(list.id, {
						...existing,
						...list,
						total_count: existing.total_count,
						pending_count: existing.pending_count,
						completed_count: existing.completed_count,
					})
				}
				break
			}

			case 'reminder_list.deleted': {
				const listId = data.id as string
				if (!listId) return
				this.#listsCache?.data.delete(listId)
				this.#remindersCache.delete(listId)
				break
			}
		}
	}

	/**
	 * recompute counts for a list from cached reminders.
	 */
	#recomputeCounts(listId: string | null): void {
		const key = this.#listKey(listId)
		const entry = this.#remindersCache.get(key)
		if (!entry) return

		const total = entry.reminders.length
		const pending = entry.reminders.filter((r) => r.status === 'pending').length
		const completed = entry.reminders.filter((r) => r.status === 'completed').length

		if (listId === null) {
			this.setDefaultCounts({
				total_count: total,
				pending_count: pending,
				completed_count: completed,
			})
		} else if (this.#listsCache) {
			const listEntry = this.#listsCache.data.get(listId)
			if (listEntry) {
				this.#listsCache.data.set(listId, {
					...listEntry,
					total_count: total,
					pending_count: pending,
					completed_count: completed,
				})
			}
		}
	}

	#isFresh(fetchedAt: number): boolean {
		return Date.now() - fetchedAt < CACHE_TTL_MS
	}

	#listKey(listId: string | null): string {
		return listId ?? 'default'
	}

	// lists

	get lists(): ReminderListWithCounts[] {
		return this.#listsCache ? [...this.#listsCache.data.values()] : []
	}

	/**
	 * set the sort mode for lists and re-fetch from server.
	 */
	setListsSortMode(mode: ReminderListsSortMode): void {
		if (mode === this.listsSortMode) return
		this.listsSortMode = mode
		this.invalidateLists()
		void this.loadLists({ force: true })
	}

	/**
	 * O(1) lookup of a list by id.
	 */
	getListById(listId: string): ReminderListWithCounts | null {
		return this.#listsCache?.data.get(listId) ?? null
	}

	get isListsFresh(): boolean {
		return this.#listsCache !== null && this.#isFresh(this.#listsCache.fetchedAt)
	}

	setLists(lists: ReminderListWithCounts[]): void {
		this.#listsCache = buildListsCache(lists, Date.now())
	}

	#parseSortMode(): { sort_by: ListSortBy; sort_dir: SortDir } {
		const [sort_by, sort_dir] = this.listsSortMode.split(':') as [ListSortBy, SortDir]
		return { sort_by, sort_dir }
	}

	async loadLists(options?: { force?: boolean }): Promise<ReminderListWithCounts[]> {
		const force = options?.force ?? false

		if (!force && this.isListsFresh) {
			return this.lists
		}

		if (this.#listsInFlight) return this.#listsInFlight

		this.#listsInFlight = (async () => {
			const { sort_by, sort_dir } = this.#parseSortMode()
			const { data, error } = await apiClient().GET('/v1/reminders/lists', {
				params: { query: { include_counts: true, sort_by, sort_dir } },
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

	// default counts (computed from default list reminders)

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

	// reminders (per list)

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

	// mutations

	/**
	 * create a new reminder list.
	 * returns the created list for navigation; WS delivers authoritative cache update.
	 */
	async createList(
		params: {
			name: string
			icon?: string | null
			color?: string | null
		},
		options?: { rollback?: boolean }
	): Promise<ReminderListWithCounts | null> {
		const doRollback = options?.rollback ?? true
		// optimistic: add placeholder list immediately
		const tempId = `temp-${Date.now()}`
		const placeholder: ReminderListWithCounts = {
			id: tempId,
			name: params.name,
			icon: params.icon ?? null,
			color: params.color ?? null,
			position: 0,
			total_count: 0,
			pending_count: 0,
			completed_count: 0,
		} as ReminderListWithCounts
		this.#listsCache?.data.set(tempId, placeholder)

		try {
			const { data, error } = await apiClient().POST('/v1/reminders/lists', {
				body: {
					name: params.name,
					icon: params.icon ?? null,
					color: params.color ?? null,
					position: 0,
				},
			})

			if (error || !data) {
				if (doRollback) this.#listsCache?.data.delete(tempId)
				showError('could not create list')
				return null
			}

			// replace placeholder with real list
			this.#listsCache?.data.delete(tempId)
			const created = toListWithCounts(data as ReminderListWithCounts)
			this.#listsCache?.data.set(created.id, created)
			this.lastVisitedListId = created.id
			this.lastVisitedPath = `/reminders/lists/${created.id}`
			return created
		} catch {
			if (doRollback) this.#listsCache?.data.delete(tempId)
			showError('could not create list')
			return null
		}
	}

	/**
	 * create a new reminder.
	 * returns the created reminder for the caller; WS delivers authoritative cache update.
	 */
	async createReminder(
		params: {
			title: string
			listId: string | null
			description?: string | null
		},
		options?: { rollback?: boolean }
	): Promise<ReminderWithSubtasks | null> {
		const doRollback = options?.rollback ?? true
		// optimistic: add placeholder reminder immediately
		const tempId = `temp-${Date.now()}`
		const placeholder: ReminderWithSubtasks = {
			id: tempId,
			title: params.title,
			description: params.description ?? null,
			list_id: params.listId,
			status: 'pending',
			position: 0,
			owner_id: '',
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
			subtasks: [],
		} as ReminderWithSubtasks
		const key = this.#listKey(params.listId)
		const entry = this.#remindersCache.get(key)
		if (entry) {
			this.#remindersCache.set(key, {
				reminders: [...entry.reminders, placeholder],
				fetchedAt: entry.fetchedAt,
			})
		}
		this.#recomputeCounts(params.listId)

		try {
			const { data, error } = await apiClient().POST('/v1/reminders', {
				body: {
					title: params.title,
					list_id: params.listId,
					description: params.description,
					status: 'pending',
					position: 0,
				},
			})

			if (error || !data) {
				if (doRollback) {
					this.#removeReminderFromCache(params.listId, tempId)
					this.#recomputeCounts(params.listId)
				}
				showError('could not create reminder')
				return null
			}

			// replace placeholder with real reminder
			const created = { ...data, subtasks: [] } as ReminderWithSubtasks
			const currentEntry = this.#remindersCache.get(key)
			if (currentEntry) {
				this.#remindersCache.set(key, {
					reminders: currentEntry.reminders.map((r) => (r.id === tempId ? created : r)),
					fetchedAt: currentEntry.fetchedAt,
				})
			}

			return created
		} catch {
			if (doRollback) {
				this.#removeReminderFromCache(params.listId, tempId)
				this.#recomputeCounts(params.listId)
			}
			showError('could not create reminder')
			return null
		}
	}

	/**
	 * complete a reminder.
	 * optimistic update; WS delivers authoritative state.
	 */
	async completeReminder(
		reminder: ReminderWithSubtasks,
		options?: { rollback?: boolean }
	): Promise<ReminderWithSubtasks | null> {
		const doRollback = options?.rollback ?? true
		const previous = this.#findReminderInCache(reminder.list_id, reminder.id) ?? reminder
		const optimistic: ReminderWithSubtasks = { ...previous, status: 'completed' }
		this.#updateReminderInCache(reminder.list_id, optimistic)

		try {
			const { error } = await apiClient().POST('/v1/reminders/{reminder_id}/complete', {
				params: { path: { reminder_id: reminder.id } },
			})

			if (error) {
				if (doRollback) this.#updateReminderInCache(reminder.list_id, previous)
				showError('could not complete reminder')
				return null
			}

			return optimistic
		} catch {
			if (doRollback) this.#updateReminderInCache(reminder.list_id, previous)
			showError('could not complete reminder')
			return null
		}
	}

	/**
	 * uncomplete a reminder (set status back to pending).
	 * optimistic update; WS delivers authoritative state.
	 */
	async uncompleteReminder(
		reminder: ReminderWithSubtasks,
		options?: { rollback?: boolean }
	): Promise<ReminderWithSubtasks | null> {
		const doRollback = options?.rollback ?? true
		const previous = this.#findReminderInCache(reminder.list_id, reminder.id) ?? reminder
		const optimistic: ReminderWithSubtasks = { ...previous, status: 'pending' }
		this.#updateReminderInCache(reminder.list_id, optimistic)

		try {
			const { error } = await apiClient().PATCH('/v1/reminders/{reminder_id}', {
				params: { path: { reminder_id: reminder.id } },
				body: { status: 'pending' },
			})

			if (error) {
				if (doRollback) this.#updateReminderInCache(reminder.list_id, previous)
				showError('could not update reminder')
				return null
			}

			return optimistic
		} catch {
			if (doRollback) this.#updateReminderInCache(reminder.list_id, previous)
			showError('could not update reminder')
			return null
		}
	}

	/**
	 * update a reminder's title/description.
	 * WS delivers authoritative state.
	 */
	async updateReminder(
		reminder: ReminderWithSubtasks,
		updates: { title?: string; description?: string | null },
		options?: { rollback?: boolean }
	): Promise<ReminderWithSubtasks | null> {
		const doRollback = options?.rollback ?? true
		const previous = this.#findReminderInCache(reminder.list_id, reminder.id) ?? reminder

		// optimistic update
		const optimistic = { ...previous, ...updates } as ReminderWithSubtasks
		this.#updateReminderInCache(reminder.list_id, optimistic)

		try {
			const { error } = await apiClient().PATCH('/v1/reminders/{reminder_id}', {
				params: { path: { reminder_id: reminder.id } },
				body: updates,
			})

			if (error) {
				if (doRollback) this.#updateReminderInCache(reminder.list_id, previous)
				showError('could not update reminder')
				return null
			}

			return optimistic
		} catch {
			if (doRollback) this.#updateReminderInCache(reminder.list_id, previous)
			showError('could not update reminder')
			return null
		}
	}

	/**
	 * delete a reminder.
	 * optimistic removal; WS confirms via refetch.
	 */
	async deleteReminder(
		reminder: ReminderWithSubtasks,
		options?: { rollback?: boolean }
	): Promise<boolean> {
		const doRollback = options?.rollback ?? true
		// optimistic removal
		const key = this.#listKey(reminder.list_id ?? null)
		const existing = this.#remindersCache.get(key)
		const snapshot = existing ? [...existing.reminders] : null

		if (existing) {
			this.#remindersCache.set(key, {
				reminders: existing.reminders.filter((r) => r.id !== reminder.id),
				fetchedAt: existing.fetchedAt,
			})
		}

		try {
			const { error } = await apiClient().DELETE('/v1/reminders/{reminder_id}', {
				params: { path: { reminder_id: reminder.id } },
			})

			if (error) {
				if (doRollback && snapshot && existing) {
					this.#remindersCache.set(key, {
						reminders: snapshot,
						fetchedAt: existing.fetchedAt,
					})
				}
				showError('could not delete reminder')
				return false
			}

			return true
		} catch {
			if (doRollback && snapshot && existing) {
				this.#remindersCache.set(key, {
					reminders: snapshot,
					fetchedAt: existing.fetchedAt,
				})
			}
			showError('could not delete reminder')
			return false
		}
	}

	/**
	 * move a reminder to a different list.
	 * optimistic move; WS delivers authoritative state.
	 */
	async moveReminder(
		reminder: ReminderWithSubtasks,
		targetListId: string | null,
		options?: { rollback?: boolean }
	): Promise<ReminderWithSubtasks | null> {
		const doRollback = options?.rollback ?? true
		const currentListId = reminder.list_id ?? null
		if (currentListId === targetListId) return reminder

		const previous = this.#findReminderInCache(currentListId, reminder.id) ?? reminder
		const optimistic: ReminderWithSubtasks = {
			...previous,
			list_id: targetListId,
		}

		// optimistic: move between caches
		this.#removeReminderFromCache(currentListId, reminder.id)
		this.#appendReminderToCache(targetListId, optimistic)

		try {
			const { error } = await apiClient().PATCH('/v1/reminders/{reminder_id}', {
				params: { path: { reminder_id: reminder.id } },
				body: { list_id: targetListId },
			})

			if (error) {
				if (doRollback) {
					this.#removeReminderFromCache(targetListId, reminder.id)
					this.#appendReminderToCache(currentListId, previous)
				}
				showError('could not move reminder')
				return null
			}

			return optimistic
		} catch {
			if (doRollback) {
				this.#removeReminderFromCache(targetListId, reminder.id)
				this.#appendReminderToCache(currentListId, previous)
			}
			showError('could not move reminder')
			return null
		}
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

	// global

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

// helpers

function toListWithCounts(list: ReminderListWithCounts | ReminderList): ReminderListWithCounts {
	if ('pending_count' in list) return list
	return { ...list, total_count: 0, pending_count: 0, completed_count: 0 }
}

// singleton export

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

	// subscribe immediately if already authenticated
	// (module may be imported after auth when navigating to /reminders)
	if (getAccessToken()) {
		reminders.init()
	}
}
