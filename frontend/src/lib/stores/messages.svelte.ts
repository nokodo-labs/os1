/**
 * messages store - people conversations (DMs + group chats) and message
 * requests. mirrors the chat store pagination but lists threads under the
 * `people` participant scope and reuses the chat thread/unread caches.
 */

import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { chat, isPeopleThread, type Thread } from '$lib/stores/chat.svelte'
import { session } from '$lib/stores/session.svelte'
import {
	STORE_EVENT_TYPES,
	storeEventData,
	storeEventString,
	subscribeToStoreEvents,
} from '$lib/stores/storeEvents'
import { SvelteSet } from 'svelte/reactivity'

/** create-thread inputs the messages app sets; owner_id is filled in here. */
export type NewThreadInput = Partial<Omit<components['schemas']['ThreadCreate'], 'owner_id'>>

const CACHE_TTL_MS = 5 * 60 * 1000

const MESSAGES_EVENT_TYPES = [
	...STORE_EVENT_TYPES.chat,
	...STORE_EVENT_TYPES.resourceAccessResource,
	...STORE_EVENT_TYPES.notifications,
] as const

class MessagesStore {
	conversations = $state<Thread[]>([])
	invites = $state<Thread[]>([])
	isLoading = $state(false)
	isLoadingMore = $state(false)
	hasMore = $state(false)
	hasLoaded = $state(false)
	/** invites are a second collection here, so they carry their own loaded signal. */
	hasLoadedInvites = $state(false)

	readonly inviteCount = $derived(this.invites.length)

	/** Thread carries no per-user state, so mute is tracked here (see `loadMuted`). */
	readonly #mutedThreadIds = new SvelteSet<string>()

	#unsubscribe: (() => void) | null = null
	#limit = 25
	#skip = 0
	/** pages already pulled in; a refetch re-reads all of them so scrolling survives a remount. */
	#loadedPages = 0
	#fetchedAt = 0

	// lifecycle

	init = (): void => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = subscribeToStoreEvents(
				MESSAGES_EVENT_TYPES,
				this.#handleStreamEvent
			)
		}
	}

	cleanup = (): void => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	clear = (): void => {
		this.conversations = []
		this.invites = []
		this.isLoading = false
		this.isLoadingMore = false
		this.hasMore = false
		this.hasLoaded = false
		this.hasLoadedInvites = false
		this.#skip = 0
		this.#loadedPages = 0
		this.#fetchedAt = 0
		this.#mutedThreadIds.clear()
	}

	invalidate = (): void => {
		this.#fetchedAt = 0
	}

	refresh = async (): Promise<void> => {
		await Promise.allSettled([this.load({ force: true }), this.loadInvites()])
	}

	// reads

	unreadCount(threadId: string): number {
		return chat.unreadCounts.get(threadId) ?? 0
	}

	isMuted(threadId: string): boolean {
		return this.#mutedThreadIds.has(threadId)
	}

	// load

	#isFresh(): boolean {
		return this.hasLoaded && Date.now() - this.#fetchedAt < CACHE_TTL_MS
	}

	/**
	 * loads the inbox, or does nothing when the cached pages are still fresh -
	 * reopening the app must not fall back to page one. a forced reload re-reads
	 * every page already pulled in, in one call.
	 */
	load = async (options?: { limit?: number; force?: boolean }): Promise<void> => {
		if (!getAccessToken()) {
			this.clear()
			return
		}
		if (!options?.force && this.#isFresh()) return
		const userId = session.currentUserId
		if (!userId) return
		const limit = options?.limit ?? this.#limit
		const pageCount = Math.max(1, this.#loadedPages)
		const fetchLimit = limit * pageCount
		this.#limit = limit
		this.isLoading = true
		try {
			const { data, error } = await api.GET('/v1/threads', {
				params: {
					query: {
						not_archived_by: userId,
						not_invite_pending_for: userId,
						participant_scope: 'people',
						limit: fetchLimit,
						skip: 0,
						sort_by: 'last_activity_at',
						sort_dir: 'desc',
						include_last_message: true,
					},
				},
			})
			// a failed refetch keeps the listed conversations: it must not read as empty.
			if (error || !data) return
			this.conversations = data
			for (const thread of data) chat.threadCache.set(thread)
			this.#skip = data.length
			this.#loadedPages = Math.max(1, Math.ceil(data.length / limit))
			this.hasMore = data.length === fetchLimit
			this.hasLoaded = true
			this.#fetchedAt = Date.now()
			void chat.fetchUnreadCounts()
			void this.loadMuted()
		} finally {
			this.isLoading = false
		}
	}

	/**
	 * seed the muted set from one extra list call - the thread payload has no
	 * per-user state, and asking per row would be N requests. only the ids are
	 * read, so this one stays off `include_last_message`.
	 */
	loadMuted = async (): Promise<void> => {
		if (!getAccessToken()) return
		const userId = session.currentUserId
		if (!userId) return
		const { data, error } = await api.GET('/v1/threads', {
			params: {
				query: {
					muted_by: userId,
					not_archived_by: userId,
					participant_scope: 'people',
					limit: 100,
					sort_by: 'last_activity_at',
					sort_dir: 'desc',
				},
			},
		})
		if (error || !data) return
		this.#mutedThreadIds.clear()
		for (const thread of data) this.#mutedThreadIds.add(thread.id)
	}

	loadMore = async (options?: { limit?: number }): Promise<void> => {
		if (!getAccessToken()) return
		if (this.isLoading || this.isLoadingMore || !this.hasMore) return
		const userId = session.currentUserId
		if (!userId) return
		const limit = options?.limit ?? this.#limit
		this.isLoadingMore = true
		try {
			const { data, error } = await api.GET('/v1/threads', {
				params: {
					query: {
						not_archived_by: userId,
						not_invite_pending_for: userId,
						participant_scope: 'people',
						limit,
						skip: this.#skip,
						sort_by: 'last_activity_at',
						sort_dir: 'desc',
						include_last_message: true,
					},
				},
			})
			if (error || !data) return
			const existing = new Set(this.conversations.map((t) => t.id))
			const next = data.filter((t) => !existing.has(t.id))
			for (const thread of data) chat.threadCache.set(thread)
			this.conversations = [...this.conversations, ...next]
			this.#skip += data.length
			this.#loadedPages += 1
			this.hasMore = data.length === limit
		} finally {
			this.isLoadingMore = false
		}
	}

	/** invite rows announce the request instead of a preview, so no last message. */
	loadInvites = async (): Promise<void> => {
		if (!getAccessToken()) return
		const userId = session.currentUserId
		if (!userId) return
		const { data } = await api.GET('/v1/threads', {
			params: {
				query: {
					invite_pending_for: userId,
					participant_scope: 'people',
					sort_by: 'last_activity_at',
					sort_dir: 'desc',
				},
			},
		})
		this.invites = data ?? []
		this.hasLoadedInvites = true
	}

	// mutations

	/**
	 * create a thread of any shape (DM, group, from a social group) through the
	 * single creation path. a DM is one member, a group is several; the backend
	 * dedupes 1:1s and friend-gates non-friends into invites.
	 */
	createThread = async (input: NewThreadInput): Promise<Thread | null> => {
		const ownerId = session.currentUserId
		if (!ownerId) return null
		const { data } = await api.POST('/v1/threads', {
			body: { owner_id: ownerId, is_temporary: false, ...input },
		})
		if (data) this.#absorbConversation(data)
		return data ?? null
	}

	/** record the mute flag a per-user state write came back with. */
	applyMuted = (threadId: string, muted: boolean): void => {
		if (muted) this.#mutedThreadIds.add(threadId)
		else this.#mutedThreadIds.delete(threadId)
	}

	/** drop a conversation from the list after archiving, leaving or deleting it. */
	removeConversation = (threadId: string): void => {
		this.conversations = this.conversations.filter((t) => t.id !== threadId)
		this.invites = this.invites.filter((t) => t.id !== threadId)
		this.#mutedThreadIds.delete(threadId)
	}

	/** merge a patch into a listed conversation, keeping its position. */
	patchConversation = (threadId: string, patch: Partial<Thread>): void => {
		const idx = this.conversations.findIndex((t) => t.id === threadId)
		if (idx === -1) return
		this.conversations = [
			...this.conversations.slice(0, idx),
			{ ...this.conversations[idx], ...patch },
			...this.conversations.slice(idx + 1),
		]
	}

	acceptInvite = async (threadId: string): Promise<Thread | null> => {
		const userId = session.currentUserId
		if (!userId) return null
		const { data } = await api.POST(
			'/v1/threads/{thread_id}/participants/users/{user_id}/invite/accept',
			{ params: { path: { thread_id: threadId, user_id: userId } } }
		)
		this.invites = this.invites.filter((t) => t.id !== threadId)
		if (data) this.#absorbConversation(data)
		return data ?? null
	}

	declineInvite = async (threadId: string): Promise<void> => {
		const userId = session.currentUserId
		if (!userId) return
		await api.POST('/v1/threads/{thread_id}/participants/users/{user_id}/invite/decline', {
			params: { path: { thread_id: threadId, user_id: userId } },
		})
		this.invites = this.invites.filter((t) => t.id !== threadId)
	}

	blockInvite = async (threadId: string): Promise<void> => {
		const userId = session.currentUserId
		if (!userId) return
		await api.POST('/v1/threads/{thread_id}/participants/users/{user_id}/invite/block', {
			params: { path: { thread_id: threadId, user_id: userId } },
		})
		this.invites = this.invites.filter((t) => t.id !== threadId)
	}

	// internals

	#absorbConversation(thread: Thread): void {
		chat.threadCache.set(thread)
		if (!isPeopleThread(thread)) return
		this.invites = this.invites.filter((t) => t.id !== thread.id)
		if (!this.conversations.some((t) => t.id === thread.id)) {
			this.conversations = [thread, ...this.conversations]
		}
	}

	#reorder(threadId: string, patch: Partial<Thread>): void {
		const idx = this.conversations.findIndex((t) => t.id === threadId)
		if (idx === -1) return
		const updated = { ...this.conversations[idx], ...patch }
		this.conversations = [
			updated,
			...this.conversations.slice(0, idx),
			...this.conversations.slice(idx + 1),
		]
	}

	#handleStreamEvent = (message: StreamMessage): void => {
		const data = storeEventData(message) ?? {}

		if (message.type === 'thread.created') {
			const thread = data as unknown as Thread
			if (!thread?.id || thread.is_temporary) return
			this.#absorbConversation(thread)
			return
		}

		if (message.type === 'thread.updated') {
			const threadId = storeEventString(message, ['id', 'thread_id'])
			if (!threadId) return
			const patch: Partial<Thread> = {}
			if (typeof data.title === 'string') patch.title = data.title
			if (typeof data.last_activity_at === 'string')
				patch.last_activity_at = data.last_activity_at
			if (typeof data.updated_at === 'string') patch.updated_at = data.updated_at
			this.#reorder(threadId, patch)
			return
		}

		if (message.type === 'thread.deleted') {
			const threadId = storeEventString(message, ['id', 'thread_id'])
			if (threadId) this.removeConversation(threadId)
			return
		}

		if (message.type === 'message.created') {
			const threadId = storeEventString(message, ['thread_id'])
			if (!threadId) return
			if (this.conversations.some((t) => t.id === threadId)) {
				const activity =
					typeof data.created_at === 'string' ? data.created_at : new Date().toISOString()
				this.#reorder(threadId, { last_activity_at: activity })
			}
			return
		}

		if (message.type === 'access.updated' || message.type === 'resource.access.updated') {
			if (data.resource_type !== 'thread' || typeof data.resource_id !== 'string') return
			const threadId = data.resource_id
			void chat.threadCache.getThread(threadId).then((thread) => {
				if (!thread) {
					this.removeConversation(threadId)
				} else if (isPeopleThread(thread)) {
					this.#absorbConversation(thread)
				}
			})
			return
		}

		if (message.type === 'notification.custom') {
			if (data.kind === 'message_request') void this.loadInvites()
		}
	}
}

export const messages = new MessagesStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			messages.init()
		} else {
			messages.cleanup()
			messages.clear()
		}
	})
}
