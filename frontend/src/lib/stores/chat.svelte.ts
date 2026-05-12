import { browser, dev } from '$app/environment'
import { api } from '$lib/api/client'
import type { CreateAndRunStreamDelta, StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import type { PendingAttachment } from '$lib/chat/types'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { STORE_EVENT_TYPES, subscribeToStoreEvents } from '$lib/stores/storeEvents'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export type Thread = components['schemas']['Thread']
export type PendingChatStart = { threadId: string; content: string }
export type PendingCreateAndRun = {
	threadId: string
	text: string
	attachments: PendingAttachment[]
	stream: AsyncGenerator<CreateAndRunStreamDelta, void, unknown>
}
type ApiMessage = components['schemas']['Message']
type ApiTask = components['schemas']['Task']

const THREAD_MAINTENANCE_TASK = 'thread.maintenance'

// cache TTL in milliseconds
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

interface ThreadCacheEntry {
	thread: Thread
	fetchedAt: number
}

interface MessageCacheEntry {
	messages: ApiMessage[]
	fetchedAt: number
	complete: boolean
	/** number of messages covered by the paginated latest-page cursor */
	pageSize: number
	/** thread.last_activity_at observed when this message snapshot was written */
	threadLastActivityAt: string | null
}

type ApiEvent = components['schemas']['Event']

interface EventCacheEntry {
	events: ApiEvent[]
	/** event IDs for O(1) deduplication */
	eventIds: Set<string>
	fetchedAt: number
	/** message IDs whose events are included in this cache entry */
	messageIds: Set<string>
}

class ThreadCache {
	readonly #threadCache = new SvelteMap<string, ThreadCacheEntry>()
	readonly #messageCache = new SvelteMap<string, MessageCacheEntry>()
	readonly #eventCache = new SvelteMap<string, EventCacheEntry>()
	readonly #prefetchInFlight = new SvelteSet<string>()
	/**
	 * per-thread local message-event timestamp. bumped whenever a
	 * message.* event arrives via WS. used by setMessages to detect
	 * stale fetches: if a write started before the latest activity,
	 * the data is potentially missing messages that arrived during
	 * the fetch (race between prefetch/loadTree and run streaming).
	 */
	readonly #lastMessageEventAt = new SvelteMap<string, number>()

	#isFresh(fetchedAt: number): boolean {
		return Date.now() - fetchedAt < CACHE_TTL_MS
	}

	get(threadId: string): Thread | null {
		const entry = this.#threadCache.get(threadId)
		if (!entry || !this.#isFresh(entry.fetchedAt)) return null
		return entry.thread
	}

	getCachedMessages(threadId: string): ApiMessage[] | null {
		return this.getCachedMessageSnapshot(threadId)?.messages ?? null
	}

	getCachedMessageSnapshot(
		threadId: string
	): { messages: ApiMessage[]; complete: boolean; pageSize: number } | null {
		const entry = this.#messageCache.get(threadId)
		if (!entry || !this.#isFresh(entry.fetchedAt)) return null

		const threadActivity = this.#threadActivityKey(threadId)
		if (
			entry.threadLastActivityAt !== null &&
			threadActivity !== null &&
			entry.threadLastActivityAt !== threadActivity
		) {
			this.#messageCache.delete(threadId)
			return null
		}

		return {
			messages: entry.messages,
			complete: entry.complete,
			pageSize: entry.pageSize,
		}
	}

	hasCachedMessage(threadId: string, messageId: string): boolean {
		const entry = this.getCachedMessageSnapshot(threadId)
		return entry?.messages.some((m) => m.id === messageId) ?? false
	}

	set(thread: Thread): void {
		this.#threadCache.set(thread.id, { thread, fetchedAt: Date.now() })
	}

	setMessages(
		threadId: string,
		messages: ApiMessage[],
		complete: boolean = false,
		fetchStartedAt?: number,
		pageSize: number = messages.length
	): boolean {
		// race guard: if any message activity happened since this fetch
		// started, the result may be missing messages that arrived during
		// the fetch. drop the write so the next read goes back to the API.
		if (fetchStartedAt !== undefined) {
			const lastActivity = this.#lastMessageEventAt.get(threadId) ?? 0
			if (lastActivity >= fetchStartedAt) {
				this.#messageCache.delete(threadId)
				return false
			}
		}
		this.#messageCache.set(threadId, {
			messages,
			fetchedAt: Date.now(),
			complete,
			pageSize,
			threadLastActivityAt: this.#threadActivityKey(threadId),
		})
		return true
	}

	#threadActivityKey(threadId: string): string | null {
		const activity = this.#threadCache.get(threadId)?.thread.last_activity_at
		return typeof activity === 'string' ? activity : null
	}

	/**
	 * mark that something changed server-side for this thread. callers
	 * should invoke this whenever a message.* event arrives, regardless
	 * of whether a cache entry exists. setMessages reads this to discard
	 * stale fetches that started before the activity.
	 */
	markActivity(threadId: string, at: number = Date.now()): void {
		const prev = this.#lastMessageEventAt.get(threadId) ?? 0
		if (at > prev) this.#lastMessageEventAt.set(threadId, at)
	}

	invalidate(threadId: string): void {
		this.#threadCache.delete(threadId)
	}

	invalidateMessages(threadId: string): void {
		this.#messageCache.delete(threadId)
	}

	invalidateAll(threadId: string): void {
		this.#threadCache.delete(threadId)
		this.#messageCache.delete(threadId)
		this.#eventCache.delete(threadId)
	}

	// -- events cache --

	getCachedEvents(
		threadId: string
	): { events: ApiEvent[]; messageIds: ReadonlySet<string> } | null {
		const entry = this.#eventCache.get(threadId)
		if (!entry || !this.#isFresh(entry.fetchedAt)) return null
		return { events: entry.events, messageIds: entry.messageIds }
	}

	setEvents(threadId: string, events: ApiEvent[], messageIds: string[]): void {
		this.#eventCache.set(threadId, {
			events,
			eventIds: new Set(events.map((e) => e.id)),
			fetchedAt: Date.now(),
			messageIds: new Set(messageIds),
		})
	}

	appendEvents(threadId: string, newEvents: ApiEvent[], newMessageIds: string[]): void {
		const entry = this.#eventCache.get(threadId)
		if (!entry || !this.#isFresh(entry.fetchedAt)) return
		const deduped = newEvents.filter((e) => !entry.eventIds.has(e.id))
		for (const id of newMessageIds) entry.messageIds.add(id)
		if (deduped.length === 0) return
		for (const ev of deduped) entry.eventIds.add(ev.id)
		this.#eventCache.set(threadId, {
			...entry,
			events: [...entry.events, ...deduped],
			fetchedAt: Date.now(),
		})
	}

	/** register message IDs as covered without adding events (e.g. after a run) */
	addCoveredMessageIds(threadId: string, messageIds: string[]): void {
		const entry = this.#eventCache.get(threadId)
		if (!entry || !this.#isFresh(entry.fetchedAt)) return
		for (const id of messageIds) entry.messageIds.add(id)
	}

	/** remove events belonging to specific messages (e.g. after message deletion) */
	removeEventsByMessageIds(threadId: string, messageIds: string[]): void {
		const entry = this.#eventCache.get(threadId)
		if (!entry) return
		const idSet = new Set(messageIds)
		const filtered = entry.events.filter((e) => !idSet.has(e.message_id ?? ''))
		if (filtered.length === entry.events.length) {
			// no events removed, just drop message IDs
			for (const id of messageIds) entry.messageIds.delete(id)
			return
		}
		const removedEventIds = entry.events.filter((e) => idSet.has(e.message_id ?? ''))
		for (const ev of removedEventIds) entry.eventIds.delete(ev.id)
		for (const id of messageIds) entry.messageIds.delete(id)
		this.#eventCache.set(threadId, { ...entry, events: filtered })
	}

	invalidateEvents(threadId: string): void {
		this.#eventCache.delete(threadId)
	}

	markAllStale(): void {
		for (const entry of this.#threadCache.values()) entry.fetchedAt = 0
		for (const entry of this.#messageCache.values()) entry.fetchedAt = 0
		for (const entry of this.#eventCache.values()) entry.fetchedAt = 0
		this.#prefetchInFlight.clear()
	}

	/** append a message to the cached array (if thread is cached). */
	addMessage(threadId: string, message: ApiMessage): void {
		const entry = this.#messageCache.get(threadId)
		if (!entry) return
		// avoid duplicates
		if (entry.messages.some((m) => m.id === message.id)) return
		this.#messageCache.set(threadId, {
			...entry,
			messages: [...entry.messages, message],
			fetchedAt: Date.now(),
			pageSize: entry.pageSize + 1,
		})
	}

	/** merge a partial update into a cached message. */
	updateMessage(threadId: string, messageId: string, patch: Partial<ApiMessage>): void {
		const entry = this.#messageCache.get(threadId)
		if (!entry) return
		const idx = entry.messages.findIndex((m) => m.id === messageId)
		if (idx === -1) return
		const updated = [...entry.messages]
		updated[idx] = { ...updated[idx], ...patch }
		this.#messageCache.set(threadId, { ...entry, messages: updated, fetchedAt: Date.now() })
	}

	/** remove messages by id from the cached array. */
	removeMessages(threadId: string, messageIds: string[]): void {
		const entry = this.#messageCache.get(threadId)
		if (!entry) return
		const idSet = new Set(messageIds)
		const filtered = entry.messages.filter((m) => !idSet.has(m.id))
		if (filtered.length === entry.messages.length) return
		const removedCount = entry.messages.length - filtered.length
		this.#messageCache.set(threadId, {
			...entry,
			messages: filtered,
			fetchedAt: Date.now(),
			pageSize: Math.max(0, entry.pageSize - removedCount),
		})
	}

	clear(): void {
		this.#threadCache.clear()
		this.#messageCache.clear()
		this.#eventCache.clear()
		this.#prefetchInFlight.clear()
		this.#lastMessageEventAt.clear()
	}

	isPrefetching(threadId: string): boolean {
		return this.#prefetchInFlight.has(threadId)
	}

	async prefetchThread(threadId: string): Promise<void> {
		if (this.get(threadId) && this.getCachedMessages(threadId)) return
		if (this.#prefetchInFlight.has(threadId)) return

		this.#prefetchInFlight.add(threadId)
		const startedAt = Date.now()
		try {
			const [threadRes, messagesRes] = await Promise.all([
				api.GET('/v1/threads/{thread_id}', {
					params: { path: { thread_id: threadId } },
				}),
				api.GET('/v1/threads/{thread_id}/messages', {
					params: {
						path: { thread_id: threadId },
						query: { skip: 0, limit: 120 },
					},
				}),
			])

			if (threadRes.data) this.set(threadRes.data)
			if (messagesRes.data) {
				this.setMessages(
					threadId,
					messagesRes.data,
					messagesRes.data.length < 120,
					startedAt
				)
			}
		} catch (err) {
			if (dev) console.warn('[ThreadCache] prefetch failed:', threadId, err)
		} finally {
			this.#prefetchInFlight.delete(threadId)
		}
	}

	async getThread(threadId: string): Promise<Thread | null> {
		const cached = this.get(threadId)
		if (cached) return cached

		const { data, error } = await api.GET('/v1/threads/{thread_id}', {
			params: { path: { thread_id: threadId } },
		})

		if (error || !data) return null
		this.set(data)
		return data
	}

	async getMessages(
		threadId: string,
		skip: number = 0,
		limit: number = 120
	): Promise<{ messages: ApiMessage[]; fromCache: boolean }> {
		if (skip === 0) {
			const cached = this.getCachedMessages(threadId)
			if (cached) return { messages: cached, fromCache: true }
		}

		const startedAt = Date.now()
		const { data, error } = await api.GET('/v1/threads/{thread_id}/messages', {
			params: {
				path: { thread_id: threadId },
				query: { skip, limit },
			},
		})

		if (error || !data) return { messages: [], fromCache: false }
		if (skip === 0) this.setMessages(threadId, data, data.length < limit, startedAt)
		return { messages: data, fromCache: false }
	}

	async refreshCached(): Promise<void> {
		const threadIds = new SvelteSet<string>()
		for (const threadId of this.#threadCache.keys()) threadIds.add(threadId)
		for (const threadId of this.#messageCache.keys()) threadIds.add(threadId)
		for (const threadId of this.#eventCache.keys()) threadIds.add(threadId)
		await Promise.allSettled([...threadIds].map((threadId) => this.prefetchThread(threadId)))
	}
}

class ChatStore {
	threadCache = new ThreadCache()
	recentThreads = $state<Thread[]>([])
	activeThread = $state<Thread | null>(null)
	pendingChatStart = $state<PendingChatStart | null>(null)
	pendingCreateAndRun = $state<PendingCreateAndRun | null>(null)
	isLoadingThreads = $state(false)
	isLoadingMoreThreads = $state(false)
	hasMoreThreads = $state(false)
	refreshVersion = $state(0)

	/** unread message counts per thread id (only threads with unread > 0) */
	readonly unreadCounts = new SvelteMap<string, number>()

	/** thread ids currently handled by a metadata maintenance task */
	readonly metadataGeneratingThreadIds = new SvelteSet<string>()

	/** in-memory drafts keyed by context id (thread id or 'home') */
	readonly drafts = new SvelteMap<string, string>()

	#unsubscribe: (() => void) | null = null
	#threadPaginationLimit = 25
	#threadPaginationSkip = 0

	#threadMetadataMissing(thread: Thread | null | undefined): boolean {
		if (!thread) return true
		return !thread.title?.trim() || !thread.tags || thread.tags.length === 0
	}

	#findKnownThread(threadId: string): Thread | null {
		if (this.activeThread?.id === threadId) return this.activeThread
		return this.recentThreads.find((thread) => thread.id === threadId) ?? null
	}

	#clearMetadataGeneratingIfReady(thread: Thread | null | undefined): void {
		if (!thread) return
		if (!this.#threadMetadataMissing(thread)) this.metadataGeneratingThreadIds.delete(thread.id)
	}

	#threadIdForMaintenanceTask(task: ApiTask | undefined): string | null {
		if (!task) return null
		const metadata = task.metadata_ ?? {}
		if (metadata.task_name !== THREAD_MAINTENANCE_TASK) return null
		if (typeof task.spawned_thread_id === 'string' && task.spawned_thread_id) {
			return task.spawned_thread_id
		}
		return typeof metadata.thread_id === 'string' && metadata.thread_id
			? metadata.thread_id
			: null
	}

	getDraft = (key: string): string => {
		return this.drafts.get(key) ?? ''
	}

	setDraft = (key: string, value: string): void => {
		if (value) {
			this.drafts.set(key, value)
		} else {
			this.drafts.delete(key)
		}
	}

	clearDraft = (key: string): void => {
		this.drafts.delete(key)
	}

	// event stream integration

	#handleStreamEvent = (message: StreamMessage): void => {
		const data =
			message.data && typeof message.data === 'object' && !Array.isArray(message.data)
				? (message.data as Record<string, unknown>)
				: {}

		if (message.type === 'thread.created') {
			const thread = data as unknown as Thread
			if (!thread?.id || thread.is_temporary) return
			// only show threads owned by the current user in the sidebar.
			// we still receive thread.created for any thread we have access to,
			// so the home sidebar must filter by ownership explicitly.
			const token = getAccessToken()
			const me = token ? getJwtUserId(token) : null
			if (me && thread.owner_id && thread.owner_id !== me) return
			// update cache + prepend to recent threads (dedup)
			this.threadCache.set(thread)
			this.#clearMetadataGeneratingIfReady(thread)
			if (!this.recentThreads.some((t) => t.id === thread.id)) {
				this.recentThreads = [thread, ...this.recentThreads]
			}
		} else if (message.type === 'thread.updated') {
			const threadId = (data.id as string) ?? (message.thread_id as string)
			if (!threadId) return

			// extract only known Thread-compatible fields from the event
			const patch: Partial<Thread> = {}
			if (typeof data.title === 'string') patch.title = data.title
			if (Array.isArray(data.tags)) {
				patch.tags = data.tags.filter((t): t is string => typeof t === 'string')
			}
			if (typeof data.updated_at === 'string') patch.updated_at = data.updated_at
			if (typeof data.last_activity_at === 'string')
				patch.last_activity_at = data.last_activity_at
			if (typeof data.is_archived === 'boolean') patch.is_archived = data.is_archived
			if (typeof data.is_temporary === 'boolean') patch.is_temporary = data.is_temporary
			if (typeof data.current_message_id === 'string')
				patch.current_message_id = data.current_message_id
			if (typeof data.owner_id === 'string') patch.owner_id = data.owner_id
			if (Array.isArray(data.projects)) patch.projects = data.projects as Thread['projects']

			// merge into cache
			const cached = this.threadCache.get(threadId)
			if (cached) {
				const updated = { ...cached, ...patch }
				this.threadCache.set(updated)
				this.#clearMetadataGeneratingIfReady(updated)
			} else {
				this.threadCache.invalidate(threadId)
			}

			this.updateRecentThread(threadId, (t) => {
				const updated = { ...t, ...patch }
				this.#clearMetadataGeneratingIfReady(updated)
				return updated
			})

			if (this.activeThread?.id === threadId) {
				this.activeThread = { ...this.activeThread, ...patch }
				this.#clearMetadataGeneratingIfReady(this.activeThread)
			}
		} else if (message.type === 'thread.deleted') {
			const threadId = (data.id as string) ?? (message.thread_id as string)
			if (!threadId) return

			this.threadCache.invalidateAll(threadId)
			this.metadataGeneratingThreadIds.delete(threadId)
			this.removeRecentThread(threadId)
			if (this.activeThread?.id === threadId) {
				this.activeThread = null
			}
		} else if (message.type === 'runs.active') {
			const runs = Array.isArray(message.data)
				? (message.data as Array<{ thread_id?: string }>)
				: []
			for (const run of runs) {
				if (
					run.thread_id &&
					this.#threadMetadataMissing(this.#findKnownThread(run.thread_id))
				) {
					this.metadataGeneratingThreadIds.add(run.thread_id)
				}
			}
		} else if (message.type === 'run.started') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (threadId && this.#threadMetadataMissing(this.#findKnownThread(threadId))) {
				this.metadataGeneratingThreadIds.add(threadId)
			}
		} else if (message.type === 'run.error' || message.type === 'run.failed') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (threadId) this.metadataGeneratingThreadIds.delete(threadId)
		} else if (message.type === 'run.completed') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (!threadId) return
			if (this.#threadMetadataMissing(this.#findKnownThread(threadId))) {
				this.metadataGeneratingThreadIds.add(threadId)
			}
		} else if (message.type === 'task.created' || message.type === 'task.updated') {
			const task = data.task as ApiTask | undefined
			const threadId = this.#threadIdForMaintenanceTask(task)
			if (threadId) this.metadataGeneratingThreadIds.add(threadId)
		} else if (
			message.type === 'task.completed' ||
			message.type === 'task.failed' ||
			message.type === 'task.cancelled'
		) {
			const task = data.task as ApiTask | undefined
			const threadId = this.#threadIdForMaintenanceTask(task)
			if (!threadId) return
			if (message.type === 'task.completed') {
				this.#clearMetadataGeneratingIfReady(this.#findKnownThread(threadId))
			} else {
				this.metadataGeneratingThreadIds.delete(threadId)
			}
		} else if (message.type === 'thread.read') {
			// another session/tab marked a thread as read - sync unread state
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (threadId) this.unreadCounts.delete(threadId)
		} else if (message.type === 'message.created') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (!threadId) return
			// bump activity FIRST so any in-flight prefetch/loadTree that
			// started before this event will discard its (now stale) result.
			this.threadCache.markActivity(threadId)
			// add to cached messages if we have data with an id
			if (data.id && typeof data.id === 'string') {
				this.threadCache.addMessage(threadId, data as unknown as ApiMessage)
			} else {
				this.threadCache.invalidateMessages(threadId)
			}
			// bump unread count for threads the user is not currently viewing
			if (this.activeThread?.id !== threadId) {
				this.unreadCounts.set(threadId, (this.unreadCounts.get(threadId) ?? 0) + 1)
			} else {
				void this.markThreadRead(threadId)
			}
		} else if (message.type === 'message.updated') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			const msgId = (data.id as string) ?? (message.message_id as string)
			if (!threadId || !msgId) return
			this.threadCache.markActivity(threadId)
			this.threadCache.updateMessage(threadId, msgId, data as Partial<ApiMessage>)
		} else if (message.type === 'message.deleted') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (!threadId) return
			this.threadCache.markActivity(threadId)
			const deletedIds = data.deleted_ids as string[] | undefined
			const msgId = (data.message_id as string) ?? (message.message_id as string)
			if (deletedIds) {
				this.threadCache.removeMessages(threadId, deletedIds)
				this.threadCache.removeEventsByMessageIds(threadId, deletedIds)
			} else if (msgId) {
				this.threadCache.removeMessages(threadId, [msgId])
				this.threadCache.removeEventsByMessageIds(threadId, [msgId])
			}
		}
	}

	init = (): void => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = subscribeToStoreEvents(
				STORE_EVENT_TYPES.chat,
				this.#handleStreamEvent
			)
		}
	}

	cleanup = (): void => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	clear = () => {
		this.threadCache.clear()
		this.recentThreads = []
		this.activeThread = null
		this.pendingChatStart = null
		this.pendingCreateAndRun = null
		this.isLoadingThreads = false
		this.isLoadingMoreThreads = false
		this.hasMoreThreads = false
		this.#threadPaginationLimit = 25
		this.#threadPaginationSkip = 0
		this.drafts.clear()
		this.unreadCounts.clear()
		this.metadataGeneratingThreadIds.clear()
	}

	invalidate = (): void => {
		this.threadCache.markAllStale()
	}

	refreshCached = async (): Promise<void> => {
		const activeThreadId = this.activeThread?.id ?? null
		const tasks: Promise<unknown>[] = [
			this.threadCache.refreshCached(),
			this.fetchUnreadCounts(),
		]
		if (this.recentThreads.length > 0) tasks.push(this.refreshThreads())
		if (activeThreadId) {
			tasks.push(
				this.threadCache.getThread(activeThreadId).then((thread) => {
					if (thread && this.activeThread?.id === activeThreadId)
						this.activeThread = thread
				})
			)
		}
		await Promise.allSettled(tasks)
		this.refreshVersion += 1
	}

	refresh = async (): Promise<void> => {
		await this.refreshCached()
	}

	consumePendingChatStart = (threadId: string): string | null => {
		const value = this.pendingChatStart
		if (!value || value.threadId !== threadId) return null
		this.pendingChatStart = null
		return value.content
	}

	consumePendingCreateAndRun = (
		threadId: string
	): AsyncGenerator<CreateAndRunStreamDelta, void, unknown> | null => {
		const value = this.pendingCreateAndRun
		if (!value || value.threadId !== threadId) return null
		this.pendingCreateAndRun = null
		return value.stream
	}

	removeRecentThread = (threadId: string) => {
		if (!threadId) return
		this.recentThreads = this.recentThreads.filter((t) => t.id !== threadId)
	}

	updateRecentThread = (threadId: string, update: (thread: Thread) => Thread) => {
		if (!threadId) return

		const threads = this.recentThreads
		const idx = threads.findIndex((t) => t.id === threadId)
		if (idx === -1) return

		const updated = update(threads[idx])
		this.recentThreads = [updated, ...threads.slice(0, idx), ...threads.slice(idx + 1)]
	}

	fetchUnreadCounts = async (): Promise<void> => {
		try {
			const { data } = await api.GET('/v1/threads/unread-counts')
			this.unreadCounts.clear()
			if (data) {
				for (const item of data) {
					if (item.unread_count > 0) {
						this.unreadCounts.set(item.thread_id, item.unread_count)
					}
				}
			}
		} catch {
			// silently ignore
		}
	}

	markThreadRead = async (threadId: string): Promise<void> => {
		if (!threadId) return
		try {
			await api.POST('/v1/threads/{thread_id}/read', {
				params: { path: { thread_id: threadId } },
			})
		} catch {
			// silently ignore - WS event will sync state
		}
	}

	refreshThreads = async (options?: { limit?: number }): Promise<void> => {
		const token = getAccessToken()
		if (!token) {
			this.recentThreads = []
			this.hasMoreThreads = false
			this.#threadPaginationSkip = 0
			return
		}

		const userId = getJwtUserId(token)
		const limit = options?.limit ?? this.#threadPaginationLimit
		this.#threadPaginationLimit = limit
		this.#threadPaginationSkip = 0
		this.isLoadingThreads = true

		try {
			const { data } = await api.GET('/v1/threads', {
				params: {
					query: {
						owner_id: userId,
						is_archived: false,
						limit,
						skip: 0,
						sort_by: 'last_activity_at',
						sort_dir: 'desc',
					},
				},
			})

			const threads = data ?? []
			this.recentThreads = threads
			for (const thread of threads) {
				this.threadCache.set(thread)
				this.#clearMetadataGeneratingIfReady(thread)
			}
			this.#threadPaginationSkip = threads.length
			this.hasMoreThreads = threads.length === limit
			// fetch unread counts alongside thread list
			void this.fetchUnreadCounts()
		} finally {
			this.isLoadingThreads = false
		}
	}

	loadMoreThreads = async (options?: { limit?: number }): Promise<void> => {
		const token = getAccessToken()
		if (!token) return
		if (this.isLoadingThreads || this.isLoadingMoreThreads || !this.hasMoreThreads) return

		const userId = getJwtUserId(token)
		const limit = options?.limit ?? this.#threadPaginationLimit
		const skip = this.#threadPaginationSkip
		this.#threadPaginationLimit = limit
		this.isLoadingMoreThreads = true

		try {
			const { data, error } = await api.GET('/v1/threads', {
				params: {
					query: {
						owner_id: userId,
						is_archived: false,
						limit,
						skip,
						sort_by: 'last_activity_at',
						sort_dir: 'desc',
					},
				},
			})

			if (error || !data) return

			const existingThreadIds = new Set(this.recentThreads.map((thread) => thread.id))
			const nextThreads = data.filter((thread) => !existingThreadIds.has(thread.id))
			for (const thread of data) {
				this.threadCache.set(thread)
				this.#clearMetadataGeneratingIfReady(thread)
			}
			this.recentThreads = [...this.recentThreads, ...nextThreads]
			this.#threadPaginationSkip += data.length
			this.hasMoreThreads = data.length === limit
		} finally {
			this.isLoadingMoreThreads = false
		}
	}
}

export const chat = new ChatStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			chat.init()
			activeRunsStore.init()
		} else {
			chat.cleanup()
			activeRunsStore.cleanup()
			chat.clear()
		}
	})
}
