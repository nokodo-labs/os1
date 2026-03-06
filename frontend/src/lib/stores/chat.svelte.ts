import { browser, dev } from '$app/environment'
import { apiClient } from '$lib/api/client'
import type { ChatStreamDelta } from '$lib/api/streaming'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export type Thread = components['schemas']['Thread']
export type PendingChatStart = { threadId: string; content: string }
export type PendingCreateAndRun = {
	threadId: string
	stream: AsyncGenerator<ChatStreamDelta, void, unknown>
}
type ApiMessage = components['schemas']['Message']

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
}

class ThreadCache {
	readonly #threadCache = new SvelteMap<string, ThreadCacheEntry>()
	readonly #messageCache = new SvelteMap<string, MessageCacheEntry>()
	readonly #prefetchInFlight = new SvelteSet<string>()

	#isFresh(fetchedAt: number): boolean {
		return Date.now() - fetchedAt < CACHE_TTL_MS
	}

	get(threadId: string): Thread | null {
		const entry = this.#threadCache.get(threadId)
		if (!entry || !this.#isFresh(entry.fetchedAt)) return null
		return entry.thread
	}

	getCachedMessages(threadId: string): ApiMessage[] | null {
		const entry = this.#messageCache.get(threadId)
		if (!entry || !this.#isFresh(entry.fetchedAt)) return null
		return entry.messages
	}

	set(thread: Thread): void {
		this.#threadCache.set(thread.id, { thread, fetchedAt: Date.now() })
	}

	setMessages(threadId: string, messages: ApiMessage[], complete: boolean = false): void {
		this.#messageCache.set(threadId, { messages, fetchedAt: Date.now(), complete })
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
		this.#messageCache.set(threadId, { ...entry, messages: updated })
	}

	/** remove messages by id from the cached array. */
	removeMessages(threadId: string, messageIds: string[]): void {
		const entry = this.#messageCache.get(threadId)
		if (!entry) return
		const idSet = new Set(messageIds)
		const filtered = entry.messages.filter((m) => !idSet.has(m.id))
		if (filtered.length === entry.messages.length) return
		this.#messageCache.set(threadId, { ...entry, messages: filtered })
	}

	clear(): void {
		this.#threadCache.clear()
		this.#messageCache.clear()
		this.#prefetchInFlight.clear()
	}

	isPrefetching(threadId: string): boolean {
		return this.#prefetchInFlight.has(threadId)
	}

	async prefetchThread(threadId: string): Promise<void> {
		if (this.get(threadId) && this.getCachedMessages(threadId)) return
		if (this.#prefetchInFlight.has(threadId)) return

		this.#prefetchInFlight.add(threadId)
		try {
			const [threadRes, messagesRes] = await Promise.all([
				apiClient().GET('/v1/threads/{thread_id}', {
					params: { path: { thread_id: threadId } },
				}),
				apiClient().GET('/v1/threads/{thread_id}/messages', {
					params: {
						path: { thread_id: threadId },
						query: { skip: 0, limit: 120 },
					},
				}),
			])

			if (threadRes.data) this.set(threadRes.data)
			if (messagesRes.data) {
				this.setMessages(threadId, messagesRes.data, messagesRes.data.length < 120)
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

		const { data, error } = await apiClient().GET('/v1/threads/{thread_id}', {
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

		const { data, error } = await apiClient().GET('/v1/threads/{thread_id}/messages', {
			params: {
				path: { thread_id: threadId },
				query: { skip, limit },
			},
		})

		if (error || !data) return { messages: [], fromCache: false }
		if (skip === 0) this.setMessages(threadId, data, data.length < limit)
		return { messages: data, fromCache: false }
	}
}

class ChatStore {
	threadCache = new ThreadCache()
	recentThreads = $state<Thread[]>([])
	activeThread = $state<Thread | null>(null)
	pendingChatStart = $state<PendingChatStart | null>(null)
	pendingCreateAndRun = $state<PendingCreateAndRun | null>(null)
	isLoadingThreads = $state(false)

	/** in-memory drafts keyed by context id (thread id or 'home') */
	readonly drafts = new SvelteMap<string, string>()

	#unsubscribe: (() => void) | null = null

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
		const data = message.data as Record<string, unknown> | undefined
		if (!data) return

		if (message.type === 'thread.created') {
			const thread = data as unknown as Thread
			if (!thread?.id || thread.is_temporary) return
			// update cache + prepend to recent threads (dedup)
			this.threadCache.set(thread)
			if (!this.recentThreads.some((t) => t.id === thread.id)) {
				this.recentThreads = [thread, ...this.recentThreads]
			}
		} else if (message.type === 'thread.updated') {
			const threadId = (data.id as string) ?? (message.thread_id as string)
			if (!threadId) return

			// merge partial update into cached thread
			const cached = this.threadCache.get(threadId)
			if (cached) {
				this.threadCache.set({ ...cached, ...(data as Partial<Thread>) } as Thread)
			} else {
				this.threadCache.invalidate(threadId)
			}

			this.updateRecentThread(threadId, (t) => ({
				...t,
				...(data as Partial<Thread>),
			}))

			if (this.activeThread?.id === threadId) {
				this.activeThread = {
					...this.activeThread,
					...(data as Partial<Thread>),
				}
			}
		} else if (message.type === 'thread.deleted') {
			const threadId = (data.id as string) ?? (message.thread_id as string)
			if (!threadId) return

			this.threadCache.invalidateAll(threadId)
			this.removeRecentThread(threadId)
		} else if (message.type === 'message.created') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (!threadId) return
			// add to cached messages if we have data with an id
			if (data.id && typeof data.id === 'string') {
				this.threadCache.addMessage(threadId, data as unknown as ApiMessage)
			} else {
				this.threadCache.invalidateMessages(threadId)
			}
		} else if (message.type === 'message.updated') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			const msgId = (data.id as string) ?? (message.message_id as string)
			if (!threadId || !msgId) return
			this.threadCache.updateMessage(threadId, msgId, data as Partial<ApiMessage>)
		} else if (message.type === 'message.deleted') {
			const threadId = (data.thread_id as string) ?? (message.thread_id as string)
			if (!threadId) return
			const deletedIds = data.deleted_ids as string[] | undefined
			const msgId = (data.message_id as string) ?? (message.message_id as string)
			if (deletedIds) {
				this.threadCache.removeMessages(threadId, deletedIds)
			} else if (msgId) {
				this.threadCache.removeMessages(threadId, [msgId])
			}
		}
	}

	initEvents = (): void => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
	}

	cleanupEvents = (): void => {
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
		this.drafts.clear()
	}

	consumePendingChatStart = (threadId: string): string | null => {
		const value = this.pendingChatStart
		if (!value || value.threadId !== threadId) return null
		this.pendingChatStart = null
		return value.content
	}

	consumePendingCreateAndRun = (
		threadId: string
	): AsyncGenerator<ChatStreamDelta, void, unknown> | null => {
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

	refreshThreads = async (options?: { limit?: number }): Promise<void> => {
		const token = getAccessToken()
		if (!token) {
			this.recentThreads = []
			return
		}

		const userId = getJwtUserId(token)
		this.isLoadingThreads = true

		try {
			const { data } = await apiClient().GET('/v1/threads', {
				params: {
					query: {
						owner_id: userId,
						is_archived: false,
						limit: options?.limit ?? 20,
						skip: 0,
						sort_by: 'last_activity_at',
						sort_dir: 'desc',
					},
				},
			})

			this.recentThreads = data ?? []
		} finally {
			this.isLoadingThreads = false
		}
	}
}

export const chat = new ChatStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			chat.initEvents()
			activeRunsStore.init()
		} else {
			chat.cleanupEvents()
			activeRunsStore.cleanup()
			chat.clear()
		}
	})
}
