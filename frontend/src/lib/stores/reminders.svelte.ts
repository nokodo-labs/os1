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
import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { showError } from '$lib/stores/notifications.svelte'
import { STORE_EVENT_TYPES, subscribeToStoreEvents } from '$lib/stores/storeEvents'
import { SvelteMap } from 'svelte/reactivity'

// types from API
export type Reminder = components['schemas']['Reminder']
export type ReminderWithSubtasks = components['schemas']['ReminderWithSubtasks']
export type ReminderList = components['schemas']['ReminderList']
export type ReminderListCreate = components['schemas']['ReminderListCreate']
export type ReminderListWithCounts = components['schemas']['ReminderListWithCounts']
export type ReminderListUpdate = components['schemas']['ReminderListUpdate']

export type Counts = {
	total_count: number
	pending_count: number
	completed_count: number
}

export type ReminderUpdate = components['schemas']['ReminderUpdate']

export type ListSortBy = 'position' | 'name' | 'created_at' | 'updated_at'
export type SortDir = 'asc' | 'desc'
export type ReminderListsSortMode = `${ListSortBy}:${SortDir}`

// cache TTL - generous since websocket keeps cache fresh
const CACHE_TTL_MS = 30 * 60 * 1000 // 30 minutes
const REMINDER_STREAM_EVENTS = [
	...STORE_EVENT_TYPES.reminders,
	...STORE_EVENT_TYPES.resourceAccessResource,
] as const

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
	readonly #pendingCreateRequests = new SvelteMap<string, number>()

	/** event stream subscription cleanup */
	#unsubscribe: (() => void) | null = null

	/** state: last visited list id for navigation continuity */
	lastVisitedListId = $state<string | null>(null)

	/** state: last visited reminders pathname for navigation continuity */
	lastVisitedPath = $state<string | null>(null)

	/** sort mode for reminder lists */
	listsSortMode = $state<ReminderListsSortMode>('position:asc')

	#pendingKey(listId: string | null, title: string): string {
		return `${this.#listKey(listId)}|${title}`
	}

	#addPendingCreateRequest(key: string): void {
		this.#pendingCreateRequests.set(key, (this.#pendingCreateRequests.get(key) ?? 0) + 1)
	}

	#removePendingCreateRequest(key: string): void {
		const remaining = (this.#pendingCreateRequests.get(key) ?? 0) - 1
		if (remaining <= 0) {
			this.#pendingCreateRequests.delete(key)
			return
		}
		this.#pendingCreateRequests.set(key, remaining)
	}

	// event stream integration

	/**
	 * initialize event stream subscription for real-time updates.
	 */
	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = subscribeToStoreEvents(
				REMINDER_STREAM_EVENTS,
				this.#handleStreamEvent
			)
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

		if (message.type === 'access.updated' || message.type === 'resource.access.updated') {
			if (data.resource_type !== 'reminder_list' || typeof data.resource_id !== 'string')
				return
			void this.#refreshList(data.resource_id)
			return
		}

		switch (message.type) {
			// reminder events
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
					const pendingKey = this.#pendingKey(listId, incoming.title)
					if ((this.#pendingCreateRequests.get(pendingKey) ?? 0) > 0) return
					const withSubtasks = { ...incoming, subtasks: incoming.subtasks ?? [] }
					this.#remindersCache.set(key, {
						reminders: [...entry.reminders, withSubtasks],
						fetchedAt: entry.fetchedAt,
					})
				} else {
					// already exists: apply authoritative data
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

			// reminder list events
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
				} else {
					void this.#refreshList(list.id)
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
		const defaultListId = this.defaultList?.id ?? null
		return listId === null || listId === defaultListId ? 'default' : listId
	}

	async #resolveListId(listId: string | null): Promise<string | null> {
		const lists = this.isListsFresh ? this.lists : await this.loadLists()
		if (listId !== null) {
			return lists.some((list) => list.id === listId) ? listId : null
		}
		return lists.find((list) => list.is_default)?.id ?? lists[0]?.id ?? null
	}

	// lists

	get lists(): ReminderListWithCounts[] {
		return this.#listsCache ? [...this.#listsCache.data.values()] : []
	}

	get hasLoaded(): boolean {
		return (
			this.#listsCache !== null ||
			this.#defaultCountsCache !== null ||
			this.#remindersCache.size > 0
		)
	}

	get defaultList(): ReminderListWithCounts | null {
		return this.lists.find((list) => list.is_default) ?? this.lists[0] ?? null
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

	async #refreshList(listId: string): Promise<void> {
		const { data, error } = await api.GET('/v1/reminder-lists/{list_id}', {
			params: { path: { list_id: listId } },
		})
		if (error || !data) {
			this.#listsCache?.data.delete(listId)
			return
		}
		this.#listsCache?.data.set(data.id, toListWithCounts(data))
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
			const { data, error } = await api.GET('/v1/reminder-lists', {
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
		if (this.#listsCache) this.#listsCache.fetchedAt = 0
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
		if (this.#defaultCountsCache) this.#defaultCountsCache.fetchedAt = 0
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
			const apiListId = await this.#resolveListId(listId)
			if (!apiListId) {
				this.setReminders(listId, [])
				return []
			}

			const { data, error, response } = await api.GET(
				'/v1/reminder-lists/{list_id}/reminders',
				{
					params: {
						path: { list_id: apiListId },
						query: {
							include_subtasks: true,
							limit: 500,
							sort_by: 'position',
							sort_dir: 'asc',
						},
					},
				}
			)
			if (error || !data) {
				if (response.status === 404) this.setReminders(listId, [])
				return this.getReminders(listId)
			}
			const reminders = data
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
		const entry = this.#remindersCache.get(key)
		if (entry) entry.fetchedAt = 0
	}

	// mutations

	/**
	 * create a new reminder list.
	 * returns the created list for navigation; WS delivers authoritative cache update.
	 */
	async createList(params: {
		name: string
		description?: string | null
		icon?: string | null
		color?: string | null
		isDefault?: boolean
		projectIds?: string[]
	}): Promise<ReminderListWithCounts | null> {
		try {
			const { data, error } = await api.POST('/v1/reminder-lists', {
				body: {
					name: params.name,
					description: params.description ?? null,
					icon: params.icon ?? null,
					color: params.color ?? null,
					position: 0,
					is_default: params.isDefault ?? false,
					project_ids: params.projectIds ?? [],
				} satisfies ReminderListCreate,
			})

			if (error || !data) {
				showError('could not create list')
				return null
			}

			const created = toListWithCounts(data as ReminderListWithCounts)
			this.#listsCache?.data.set(created.id, created)
			this.lastVisitedListId = created.id
			this.lastVisitedPath = `/reminders/lists/${created.id}`
			return created
		} catch {
			showError('could not create list')
			return null
		}
	}

	/**
	 * delete a reminder list.
	 * optimistic removal; WS confirms via reminder_list.deleted event.
	 */
	async deleteList(listId: string): Promise<boolean> {
		const snapshot = this.#listsCache?.data.get(listId)
		this.#listsCache?.data.delete(listId)
		this.#remindersCache.delete(listId)

		try {
			const { error } = await api.DELETE('/v1/reminder-lists/{list_id}', {
				params: { path: { list_id: listId } },
			})
			if (error) {
				if (snapshot && this.#listsCache) this.#listsCache.data.set(listId, snapshot)
				showError('could not delete list')
				return false
			}
			return true
		} catch {
			if (snapshot && this.#listsCache) this.#listsCache.data.set(listId, snapshot)
			showError('could not delete list')
			return false
		}
	}

	/**
	 * update a reminder list.
	 * optimistic update; WS delivers authoritative state.
	 */
	async updateList(
		list: ReminderListWithCounts,
		updates: ReminderListUpdate,
		options?: { rollback?: boolean }
	): Promise<ReminderListWithCounts | null> {
		const doRollback = options?.rollback ?? true
		const previous = this.#listsCache?.data.get(list.id) ?? list
		const optimistic: ReminderListWithCounts = {
			...previous,
			...updates,
			total_count: previous.total_count,
			pending_count: previous.pending_count,
			completed_count: previous.completed_count,
		}
		this.#listsCache?.data.set(list.id, optimistic)

		try {
			const { data, error } = await api.PATCH('/v1/reminder-lists/{list_id}', {
				params: { path: { list_id: list.id } },
				body: updates,
			})

			if (error) {
				if (doRollback) this.#listsCache?.data.set(list.id, previous)
				showError('could not save list')
				return null
			}

			if (data) {
				const saved: ReminderListWithCounts = {
					...previous,
					...data,
					total_count: previous.total_count,
					pending_count: previous.pending_count,
					completed_count: previous.completed_count,
				}
				this.#listsCache?.data.set(list.id, saved)
				return saved
			}

			return optimistic
		} catch {
			if (doRollback) this.#listsCache?.data.set(list.id, previous)
			showError('could not save list')
			return null
		}
	}

	/**
	 * create a new reminder.
	 * returns the created reminder for the caller; WS delivers authoritative cache update.
	 */
	async createReminder(params: {
		title: string
		listId: string | null
		description?: string | null
	}): Promise<ReminderWithSubtasks | null> {
		const apiListId = await this.#resolveListId(params.listId)
		if (!apiListId) {
			showError('could not create reminder')
			return null
		}
		const key = this.#listKey(params.listId)
		const pendingKey = this.#pendingKey(params.listId, params.title)
		this.#addPendingCreateRequest(pendingKey)

		try {
			const { data, error } = await api.POST('/v1/reminder-lists/{list_id}/reminders', {
				params: { path: { list_id: apiListId } },
				body: {
					title: params.title,
					description: params.description,
					status: 'pending',
					position: 0,
				},
			})

			if (error || !data) {
				this.#removePendingCreateRequest(pendingKey)
				showError('could not create reminder')
				return null
			}

			const created: ReminderWithSubtasks = { ...data, subtasks: [] }
			const currentEntry = this.#remindersCache.get(key)
			if (currentEntry) {
				const hasReal = currentEntry.reminders.some((r) => r.id === created.id)
				if (!hasReal) {
					this.#remindersCache.set(key, {
						reminders: [...currentEntry.reminders, created],
						fetchedAt: currentEntry.fetchedAt,
					})
				}
			}
			this.#removePendingCreateRequest(pendingKey)
			this.#recomputeCounts(params.listId)

			return created
		} catch {
			this.#removePendingCreateRequest(pendingKey)
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
			const { error } = await api.POST(
				'/v1/reminder-lists/{list_id}/reminders/{reminder_id}/complete',
				{
					params: { path: { list_id: reminder.list_id, reminder_id: reminder.id } },
				}
			)

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
			const { error } = await api.PATCH(
				'/v1/reminder-lists/{list_id}/reminders/{reminder_id}',
				{
					params: { path: { list_id: reminder.list_id, reminder_id: reminder.id } },
					body: { status: 'pending' },
				}
			)

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
	 * update a reminder.
	 * WS delivers authoritative state.
	 */
	async updateReminder(
		reminder: ReminderWithSubtasks,
		updates: ReminderUpdate
	): Promise<ReminderWithSubtasks | null> {
		const previous = this.#findReminderInCache(reminder.list_id, reminder.id) ?? reminder
		const updated = this.#applyReminderUpdate(previous, updates)

		try {
			const { data, error } = await api.PATCH(
				'/v1/reminder-lists/{list_id}/reminders/{reminder_id}',
				{
					params: { path: { list_id: reminder.list_id, reminder_id: reminder.id } },
					body: updates,
				}
			)

			if (error) {
				showError('could not update reminder')
				return null
			}

			if (data) {
				const saved: ReminderWithSubtasks = {
					...previous,
					...data,
					subtasks: previous.subtasks,
				}
				this.#updateReminderInCache(reminder.list_id, saved)
				return saved
			}

			this.#updateReminderInCache(reminder.list_id, updated)
			return updated
		} catch {
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
			const { error } = await api.DELETE(
				'/v1/reminder-lists/{list_id}/reminders/{reminder_id}',
				{
					params: { path: { list_id: reminder.list_id, reminder_id: reminder.id } },
				}
			)

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
		const targetApiListId = await this.#resolveListId(targetListId)
		if (!targetApiListId) {
			showError('could not move reminder')
			return null
		}
		if (currentListId === targetApiListId) return reminder

		const previous = this.#findReminderInCache(currentListId, reminder.id) ?? reminder
		const optimistic: ReminderWithSubtasks = {
			...previous,
			list_id: targetApiListId,
		}

		// optimistic: move between caches
		this.#removeReminderFromCache(currentListId, reminder.id)
		this.#appendReminderToCache(targetListId, optimistic)

		try {
			const { error } = await api.PATCH(
				'/v1/reminder-lists/{list_id}/reminders/{reminder_id}',
				{
					params: { path: { list_id: reminder.list_id, reminder_id: reminder.id } },
					body: { list_id: targetApiListId },
				}
			)

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

	#applyReminderUpdate(
		previous: ReminderWithSubtasks,
		updates: ReminderUpdate
	): ReminderWithSubtasks {
		return {
			...previous,
			title: updates.title ?? previous.title,
			description: 'description' in updates ? updates.description : previous.description,
			due_at: 'due_at' in updates ? updates.due_at : previous.due_at,
			remind_at: 'remind_at' in updates ? updates.remind_at : previous.remind_at,
			recurrence: 'recurrence' in updates ? updates.recurrence : previous.recurrence,
			status: updates.status ?? previous.status,
			parent_id: 'parent_id' in updates ? updates.parent_id : previous.parent_id,
			position: updates.position ?? previous.position,
			list_id: updates.list_id ?? previous.list_id,
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
		this.invalidateLists()
		this.invalidateDefaultCounts()
		for (const entry of this.#remindersCache.values()) entry.fetchedAt = 0
	}

	invalidate(): void {
		this.invalidateAll()
	}

	async refreshCached(): Promise<void> {
		const tasks: Promise<unknown>[] = []
		if (this.#listsCache) tasks.push(this.loadLists({ force: true }))
		if (this.#defaultCountsCache) tasks.push(this.loadDefaultCounts({ force: true }))
		for (const key of this.#remindersCache.keys()) {
			tasks.push(this.loadReminders(key === 'default' ? null : key, { force: true }))
		}
		await Promise.allSettled(tasks)
	}

	async refresh(): Promise<void> {
		await this.refreshCached()
	}

	/**
	 * clear all caches (e.g., on logout).
	 */
	clear(): void {
		this.#listsCache = null
		this.#defaultCountsCache = null
		this.#remindersCache.clear()
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
