import { browser, dev } from '$app/environment'
import { api } from '$lib/api/client'
import type { CreateAndRunStreamDelta, StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import {
	BRANCH_PAGE_LIMIT,
	branchPageMessages,
	branchPagingOf,
	fetchBranchPage,
	type BranchPaging,
} from '$lib/chat/branchPage'
import type { ReadCursor } from '$lib/chat/readReceipts'
import type { PendingAttachment } from '$lib/chat/types'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { STORE_EVENT_TYPES, subscribeToStoreEvents } from '$lib/stores/storeEvents'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export type Thread = components['schemas']['Thread']

type ThreadParticipant = NonNullable<Thread['participants']>[number]

/** 1 writer = normal chat, 2 = DM, more = group chat. a UI distinction only. */
export type ThreadKind = 'solo' | 'direct' | 'group'

/** writers shape a thread; readers are spectators and do not. */
function canWrite(participant: ThreadParticipant): boolean {
	return (
		participant.is_owner ||
		participant.access_level === 'editor' ||
		participant.access_level === 'admin'
	)
}

/** distinct users who can write. a writer group's members are not in the payload, so they are not listed here. */
export function threadWriterUserIds(thread: Thread | null): string[] {
	const writerIds: string[] = []
	for (const participant of thread?.participants ?? []) {
		if (participant.kind !== 'user' || !canWrite(participant)) continue
		if (!writerIds.includes(participant.user.id)) writerIds.push(participant.user.id)
	}
	return writerIds
}

export function threadWriterCount(thread: Thread): number {
	return threadWriterUserIds(thread).length
}

export function threadKind(thread: Thread): ThreadKind {
	const hasWriterGroup = (thread.participants ?? []).some(
		(participant) => participant.kind === 'group' && canWrite(participant)
	)
	if (hasWriterGroup) return 'group'
	const writers = threadWriterCount(thread)
	if (writers <= 1) return 'solo'
	return writers === 2 ? 'direct' : 'group'
}

/** a thread is a "people" conversation when more than one user can write in it. */
export function isPeopleThread(thread: Thread): boolean {
	return threadKind(thread) !== 'solo'
}

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
const CHAT_STREAM_EVENTS = [
	...STORE_EVENT_TYPES.chat,
	...STORE_EVENT_TYPES.resourceAccessResource,
	...STORE_EVENT_TYPES.typing,
] as const

/**
 * how long one typing signal keeps somebody listed as composing.
 *
 * the composer re-signals every 3s while there is text (`createTypingSignal`,
 * `TYPING_HEARTBEAT_MS`), so a live composer always refreshes inside this window
 * and a signal that stops arriving - tab closed, connection lost, message sent
 * elsewhere - expires on its own rather than leaving a stuck indicator.
 */
const TYPING_TTL_MS = 8000

// cache TTL in milliseconds
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

/** shared empty result for threads no receipt has been seen for. */
const NO_CURSORS: ReadonlyMap<string, ReadCursor> = new Map()

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
	/** where this window sits in the branch, so a cache hit can keep paging */
	branch: BranchPaging | null
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

/** the flat message list endpoint rejects anything larger and 422s. */
const MESSAGE_LIST_PAGE_LIMIT = 200
/** hard stop so a page that stops advancing cannot spin the loop. */
const MESSAGE_LIST_MAX_PAGES = 50

class ThreadCache {
	readonly #threadCache = new SvelteMap<string, ThreadCacheEntry>()
	readonly #messageCache = new SvelteMap<string, MessageCacheEntry>()
	readonly #eventCache = new SvelteMap<string, EventCacheEntry>()
	readonly #prefetchInFlight = new SvelteMap<string, Promise<void>>()
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

	getCachedMessageSnapshot(threadId: string): {
		messages: ApiMessage[]
		complete: boolean
		pageSize: number
		branch: BranchPaging | null
	} | null {
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
			branch: entry.branch,
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
		pageSize: number = messages.length,
		branch: BranchPaging | null = null
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
			branch,
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

	/**
	 * settle any prefetch already running for this thread.
	 *
	 * a hover starts the prefetch and the click that follows starts the loader,
	 * so without this the two race and fetch the same thread and branch page
	 * twice - the prefetch always losing.
	 */
	async awaitPrefetch(threadId: string): Promise<void> {
		await this.#prefetchInFlight.get(threadId)
	}

	async prefetchThread(threadId: string): Promise<void> {
		if (this.get(threadId) && this.getCachedMessages(threadId)) return
		const running = this.#prefetchInFlight.get(threadId)
		if (running) return running

		const startedAt = Date.now()
		const request = (async () => {
			try {
				// the same branch page the thread loader reads back, so a prefetch
				// warms the cache instead of seeding it with a branch-blind list.
				const [threadRes, branchRes] = await Promise.all([
					api.GET('/v1/threads/{thread_id}', {
						params: { path: { thread_id: threadId } },
					}),
					fetchBranchPage(threadId),
				])

				if (threadRes.data) this.set(threadRes.data)
				const page = branchRes.page
				if (page) {
					this.setMessages(
						threadId,
						branchPageMessages(page),
						!page.has_toward_root,
						startedAt,
						page.messages.length,
						branchPagingOf(page)
					)
				}
			} catch (err) {
				if (dev) console.warn('[ThreadCache] prefetch failed:', threadId, err)
			}
		})()

		this.#prefetchInFlight.set(threadId, request)
		try {
			await request
		} finally {
			if (this.#prefetchInFlight.get(threadId) === request) {
				this.#prefetchInFlight.delete(threadId)
			}
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

	/**
	 * the selected branch, newest `limit` messages, oldest first.
	 *
	 * a bounded read for exports and snapshots. it pages the branch rather than
	 * the flat `/messages` list (which is branch-blind and capped at 200) and
	 * never writes the message cache: the thread loader owns that entry, and a
	 * 500-message export would otherwise overwrite the window it is paging.
	 */
	async getBranchMessages(threadId: string, limit: number): Promise<ApiMessage[]> {
		const collected: ApiMessage[] = []
		let cursor: string | undefined

		while (collected.length < limit) {
			const { page } = await fetchBranchPage(threadId, {
				limit: Math.min(BRANCH_PAGE_LIMIT, limit - collected.length),
				cursor,
			})
			if (!page) break
			// pages walk toward the root, so each one is older than the last
			collected.unshift(...page.messages)
			const next = page.has_toward_root ? (page.cursor_toward_root ?? null) : null
			if (!next) break
			cursor = next
		}

		return collected
	}

	/**
	 * every message in the thread, abandoned branches included, oldest first.
	 *
	 * the branch-blind counterpart to getBranchMessages, for a whole-tree export.
	 * the flat `/messages` list caps its page at 200, so this walks it with
	 * skip/limit, and like getBranchMessages it never writes the message cache.
	 */
	async getAllMessages(threadId: string, limit: number): Promise<ApiMessage[]> {
		const collected: ApiMessage[] = []

		for (let page = 0; page < MESSAGE_LIST_MAX_PAGES; page++) {
			const pageLimit = Math.min(MESSAGE_LIST_PAGE_LIMIT, limit - collected.length)
			if (pageLimit < 1) break

			const { data, error } = await api.GET('/v1/threads/{thread_id}/messages', {
				params: {
					path: { thread_id: threadId },
					query: { skip: collected.length, limit: pageLimit, sort_dir: 'asc' },
				},
			})
			if (error || !data || data.length === 0) break

			collected.push(...data)
			// a short page is the last one
			if (data.length < pageLimit) break
		}

		return collected
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
	hasLoaded = $state(false)
	/** last thread-list load failure, so the sidebar can stop showing a loader */
	error = $state<string | null>(null)
	refreshVersion = $state(0)

	/** unread message counts per thread id (only threads with unread > 0) */
	readonly unreadCounts = new SvelteMap<string, number>()

	/**
	 * read cursors per thread: user id -> the message they have read, and when
	 * this session watched them reach it.
	 *
	 * fed only by the live `thread.participants.*` fanout - there is no GET for
	 * cursors yet (B16), so this is empty on a cold open and fills in as people
	 * read. absence means UNKNOWN, never unread: see `$lib/chat/readReceipts`.
	 * for the same reason cursors can silently go stale across a WS gap, which
	 * is B19's replay problem rather than something to refetch here.
	 */
	readonly readCursors = new SvelteMap<string, SvelteMap<string, ReadCursor>>()

	/** thread ids currently handled by a metadata maintenance task */
	readonly metadataGeneratingThreadIds = new SvelteSet<string>()

	/**
	 * who is composing right now: thread id -> user id -> when the signal expires.
	 *
	 * ephemeral and never fetched: the backend fans typing out to everyone with
	 * access to the thread and excludes the sender, so this fills in live and
	 * empties itself through `TYPING_TTL_MS`.
	 */
	readonly composingUsers = new SvelteMap<string, SvelteMap<string, number>>()

	/** in-memory drafts keyed by context id (thread id or 'home') */
	readonly drafts = new SvelteMap<string, string>()

	#unsubscribe: (() => void) | null = null
	#threadPaginationLimit = 25
	#threadPaginationSkip = 0
	/** expiry timers for live typing signals, keyed `threadId:userId` */
	#typingTimers = new Map<string, ReturnType<typeof setTimeout>>()

	/** id of the signed-in user, or null when there is no usable token */
	#currentUserId(): string | null {
		const token = getAccessToken()
		return token ? getJwtUserId(token) : null
	}

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
		const metadata = task.metadata ?? {}
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

	/** cursors known for a thread this session; empty until receipts arrive. */
	threadReadCursors = (threadId: string): ReadonlyMap<string, ReadCursor> => {
		return this.readCursors.get(threadId) ?? NO_CURSORS
	}

	/** user ids composing in a thread right now; never includes your own. */
	composingUserIds = (threadId: string): string[] => {
		const composers = this.composingUsers.get(threadId)
		if (!composers) return []
		const now = Date.now()
		const ids: string[] = []
		for (const [userId, expiresAt] of composers) {
			if (expiresAt > now) ids.push(userId)
		}
		return ids
	}

	#forgetComposer = (threadId: string, userId: string): void => {
		const composers = this.composingUsers.get(threadId)
		if (composers) {
			composers.delete(userId)
			if (composers.size === 0) this.composingUsers.delete(threadId)
		}
		const key = `${threadId}:${userId}`
		const timer = this.#typingTimers.get(key)
		if (timer) clearTimeout(timer)
		this.#typingTimers.delete(key)
	}

	#clearComposing = (): void => {
		for (const timer of this.#typingTimers.values()) clearTimeout(timer)
		this.#typingTimers.clear()
		this.composingUsers.clear()
	}

	// event stream integration

	/**
	 * a participant-state change: a shared read cursor, or the subject's own
	 * private mute/pin/archive flags. only the former carries a cursor, so the
	 * key's presence - not the event type - decides whether this is a receipt.
	 */
	#applyParticipantState = (data: Record<string, unknown>, message: StreamMessage): void => {
		const threadId =
			typeof data.thread_id === 'string'
				? data.thread_id
				: typeof message.thread_id === 'string'
					? message.thread_id
					: null
		const userId = typeof data.user_id === 'string' ? data.user_id : null
		if (!threadId || !userId || data.kind !== 'user') return
		if (!('last_read_message_id' in data)) return

		const cursor =
			typeof data.last_read_message_id === 'string' ? data.last_read_message_id : null
		if (cursor) {
			const cursors = this.readCursors.get(threadId) ?? new SvelteMap<string, ReadCursor>()
			// the fanout carries no read time, so the arrival IS the only moment
			// we can honestly name. a repeat of the same cursor is not a new read
			// and keeps the stamp it already had.
			const known = cursors.get(userId)
			if (!known || known.messageId !== cursor) {
				cursors.set(userId, { messageId: cursor, at: new Date() })
			}
			this.readCursors.set(threadId, cursors)
		}

		// own cursor advancing means another session/tab read the thread.
		if (userId === this.#currentUserId()) this.unreadCounts.delete(threadId)
	}

	/**
	 * somebody else started or stopped composing in a thread.
	 *
	 * a start refreshes the expiry rather than stacking, so a composer who keeps
	 * typing stays listed and one who goes quiet drops out on the timer. only
	 * people signal: an event without a user id is not a person composing.
	 */
	#applyTypingSignal = (data: Record<string, unknown>, message: StreamMessage): void => {
		const threadId =
			typeof data.thread_id === 'string'
				? data.thread_id
				: typeof message.thread_id === 'string'
					? message.thread_id
					: null
		const userId = typeof data.user_id === 'string' ? data.user_id : null
		if (!threadId || !userId) return
		// your own composing is the composer you are looking at, never a bubble.
		if (userId === this.#currentUserId()) return

		if (message.type === 'typing.stop' || message.type === 'typing.user.stop') {
			this.#forgetComposer(threadId, userId)
			return
		}

		const composers = this.composingUsers.get(threadId) ?? new SvelteMap<string, number>()
		composers.set(userId, Date.now() + TYPING_TTL_MS)
		this.composingUsers.set(threadId, composers)

		const key = `${threadId}:${userId}`
		const previous = this.#typingTimers.get(key)
		if (previous) clearTimeout(previous)
		this.#typingTimers.set(
			key,
			setTimeout(() => this.#forgetComposer(threadId, userId), TYPING_TTL_MS)
		)
	}

	#handleStreamEvent = (message: StreamMessage): void => {
		const data =
			message.data && typeof message.data === 'object' && !Array.isArray(message.data)
				? (message.data as Record<string, unknown>)
				: {}

		if (message.type.startsWith('typing.')) {
			this.#applyTypingSignal(data, message)
			return
		}

		if (message.type === 'access.updated' || message.type === 'resource.access.updated') {
			if (data.resource_type !== 'thread' || typeof data.resource_id !== 'string') return
			const resourceId = data.resource_id
			void this.threadCache.getThread(resourceId).then((thread) => {
				if (!thread) {
					this.threadCache.invalidate(resourceId)
					this.removeRecentThread(resourceId)
					if (this.activeThread?.id === resourceId) this.activeThread = null
				}
			})
			return
		}

		if (message.type === 'thread.created') {
			const thread = data as unknown as Thread
			if (!thread?.id || thread.is_temporary) return
			// the home sidebar shows only solo chats (owned by the current user
			// with fewer than two humans). people conversations live in the
			// messages app, so filter them out here by ownership + human count.
			const token = getAccessToken()
			const me = token ? getJwtUserId(token) : null
			if (me && thread.owner_id && thread.owner_id !== me) return
			if (isPeopleThread(thread)) return
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
			if (typeof data.is_temporary === 'boolean') patch.is_temporary = data.is_temporary
			if (typeof data.current_message_id === 'string')
				patch.current_message_id = data.current_message_id
			if (typeof data.owner_id === 'string') patch.owner_id = data.owner_id
			if (Array.isArray(data.project_ids)) {
				patch.project_ids = data.project_ids.filter(
					(projectId): projectId is string => typeof projectId === 'string'
				)
			}
			if (Array.isArray(data.projects)) patch.projects = data.projects as Thread['projects']

			// merge into cache
			const cached = this.threadCache.get(threadId)
			if (cached) {
				const updated = { ...cached, ...patch }
				this.threadCache.set(updated)
				this.#clearMetadataGeneratingIfReady(updated)
			} else {
				this.threadCache.invalidate(threadId)
				void this.threadCache.getThread(threadId)
			}

			// only reorder to front if last_activity_at actually advanced
			const activityChanged =
				typeof data.last_activity_at === 'string' &&
				(() => {
					const existing = this.recentThreads.find((t) => t.id === threadId)
					return !existing || data.last_activity_at! > (existing.last_activity_at ?? '')
				})()

			this.updateRecentThread(
				threadId,
				(t) => {
					const updated = { ...t, ...patch }
					this.#clearMetadataGeneratingIfReady(updated)
					return updated
				},
				activityChanged
			)

			if (this.activeThread?.id === threadId) {
				this.activeThread = { ...this.activeThread, ...patch }
				this.#clearMetadataGeneratingIfReady(this.activeThread)
			}
		} else if (message.type === 'thread.deleted') {
			const threadId = (data.id as string) ?? (message.thread_id as string)
			if (!threadId) return

			this.threadCache.invalidateAll(threadId)
			this.metadataGeneratingThreadIds.delete(threadId)
			this.readCursors.delete(threadId)
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
		} else if (message.type === 'run.error') {
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
		} else if (
			message.type === 'thread.participants.added' ||
			message.type === 'thread.participants.updated'
		) {
			this.#applyParticipantState(data, message)
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
			this.#unsubscribe = subscribeToStoreEvents(CHAT_STREAM_EVENTS, this.#handleStreamEvent)
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
		this.hasLoaded = false
		this.error = null
		this.#threadPaginationLimit = 25
		this.#threadPaginationSkip = 0
		this.drafts.clear()
		this.unreadCounts.clear()
		this.readCursors.clear()
		this.metadataGeneratingThreadIds.clear()
		this.#clearComposing()
	}

	invalidate = (): void => {
		this.threadCache.markAllStale()
	}

	/**
	 * re-read what is on screen after a gap in the live stream.
	 *
	 * invalidation already marked every cached thread stale, so re-opening one
	 * refetches on its own - refetching all of them here would fire a branch
	 * page per cached thread. only the sidebar list, its badges and the open
	 * thread (through `refreshVersion`, which the thread page watches) are read
	 * back.
	 */
	refreshCached = async (): Promise<void> => {
		// refreshThreads reads the badges back itself
		await (this.recentThreads.length > 0 ? this.refreshThreads() : this.fetchUnreadCounts())
		this.refreshVersion += 1
	}

	refresh = async (): Promise<void> => {
		await this.refreshCached()
	}

	/**
	 * warm a thread the reader is about to open (sidebar hover).
	 *
	 * the prefetch fills the cache with the TAIL page, which is the page a
	 * caught-up reader gets. a reader with unread messages opens on their
	 * last-read page instead, so every request the prefetch makes would be
	 * thrown away - skip it rather than pay for a page nobody reads.
	 */
	prefetchThread = async (threadId: string): Promise<void> => {
		if ((this.unreadCounts.get(threadId) ?? 0) > 0) return
		await this.threadCache.prefetchThread(threadId)
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

	updateRecentThread = (
		threadId: string,
		update: (thread: Thread) => Thread,
		reorder: boolean = true
	) => {
		if (!threadId) return

		const threads = this.recentThreads
		const idx = threads.findIndex((t) => t.id === threadId)
		if (idx === -1) return

		const updated = update(threads[idx])
		if (reorder) {
			this.recentThreads = [updated, ...threads.slice(0, idx), ...threads.slice(idx + 1)]
		} else {
			this.recentThreads = [...threads.slice(0, idx), updated, ...threads.slice(idx + 1)]
		}
	}

	fetchUnreadCounts = async (): Promise<void> => {
		const userId = this.#currentUserId()
		if (!userId) return
		try {
			const { data } = await api.GET('/v1/threads/unread-counts/{user_id}', {
				params: { path: { user_id: userId } },
			})
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
		const userId = this.#currentUserId()
		if (!userId) return
		try {
			await api.POST('/v1/threads/{thread_id}/participants/users/{user_id}/read', {
				params: { path: { thread_id: threadId, user_id: userId } },
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
		this.error = null

		try {
			const { data, error } = await api.GET('/v1/threads', {
				params: {
					query: {
						owner_id: userId,
						not_archived_by: userId,
						not_invite_pending_for: userId,
						participant_scope: 'solo',
						limit,
						skip: 0,
						sort_by: 'last_activity_at',
						sort_dir: 'desc',
					},
				},
			})

			// on failure keep prior threads; an error must not render as empty.
			if (error || !data) {
				this.error = 'failed to load chats'
				return
			}

			this.recentThreads = data
			for (const thread of data) {
				this.threadCache.set(thread)
				this.#clearMetadataGeneratingIfReady(thread)
			}
			this.#threadPaginationSkip = data.length
			this.hasMoreThreads = data.length === limit
			this.hasLoaded = true
			// fetch unread counts alongside thread list
			void this.fetchUnreadCounts()
		} catch {
			this.error = 'failed to load chats'
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
						not_archived_by: userId,
						not_invite_pending_for: userId,
						participant_scope: 'solo',
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
