/**
 * data loading - events, message ingestion, pagination, tree loading, cache sync.
 */

import { api } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { chat as chatStore, type Thread } from '$lib/stores/chat.svelte'
import { resolveResourceAccessLevels } from '$lib/stores/resourceAccess.svelte'
import { session } from '$lib/stores/session.svelte'
import { parseToolCalls, parseToolEvent, parseToolResult } from '$lib/tools'
import { tick } from 'svelte'
import {
	branchPageMessages,
	branchPagingOf,
	fetchBranchPage,
	type BranchPage,
	type BranchPaging,
} from './branchPage'
import { extractAttachmentRefs, getMessageCreatedAt, type ApiMessage } from './helpers'
import { parseRunActivityEvent } from './runActivities'
import { parseRunFailureEvent } from './runFailures'
import { getMessageSteeringRunId, getMessageSteeringState } from './steering'
import { parseChatSystemEvents } from './systemEvents'
import type { ChatContext } from './types'

type ApiEvent = components['schemas']['Event']
type ApiEventPage = components['schemas']['CursorPage_Event_']
type ThreadUserState = components['schemas']['ThreadUserState']

/** max message ids the by-message-ids endpoint accepts per request */
const EVENT_MESSAGE_ID_CHUNK = 500

/** max events the by-message-ids endpoint returns per page */
const EVENT_PAGE_LIMIT = 1000

export class ThreadNotFoundError extends Error {
	constructor(threadId: string) {
		super(`thread not found: ${threadId}`)
		this.name = 'ThreadNotFoundError'
	}
}

/** where a thread page should open. */
export interface LoadTreeOptions {
	/**
	 * message to open at: the endpoint answers with the page holding it. null
	 * pins the live tail. omitting the options object entirely resolves the
	 * caller's own last-read message instead.
	 */
	anchorMessageId: string | null
}

/**
 * apply the true per-message branch counts a page carries.
 *
 * `sibling_counts` gives the FULL count for every forked message on the page
 * even when only the first few branches were carried, so a "1/3" indicator
 * renders from the page alone.
 */
function absorbSiblingCounts(paging: BranchPaging, ctx: ChatContext): void {
	for (const [parentId, total] of paging.siblingCounts) {
		ctx.siblingCounts.set(parentId, total)
	}
}

/**
 * apply a page's paging state.
 *
 * each end is taken only from a page that actually moved that way: a page
 * loaded while scrolling up always reports messages toward the leaf, but those
 * are the ones already on screen, not ones still to load.
 */
function absorbBranchPaging(
	paging: BranchPaging,
	ctx: ChatContext,
	ends: 'both' | 'root' | 'leaf'
): void {
	if (ends !== 'leaf') {
		ctx.branchCursorTowardRoot = paging.cursorTowardRoot
		ctx.hasMoreMessages = paging.hasTowardRoot
	}
	if (ends !== 'root') {
		ctx.branchCursorTowardLeaf = paging.cursorTowardLeaf
		ctx.hasNewerMessages = paging.hasTowardLeaf
	}
	absorbSiblingCounts(paging, ctx)
}

function absorbBranchPage(
	page: BranchPage,
	ctx: ChatContext,
	ends: 'both' | 'root' | 'leaf'
): void {
	absorbBranchPaging(branchPagingOf(page), ctx, ends)
}

/** replay parsed events into the chat context (tools, run activities, attachments) */
function replayEvents(events: ApiEvent[], ctx: ChatContext): void {
	for (const ev of events) {
		const toolEv = parseToolEvent({
			id: ev.id,
			type: ev.type,
			data: (ev.data ?? {}) as Record<string, unknown>,
			created_at: ev.created_at ?? undefined,
			message_id: ev.message_id ?? undefined,
		})
		if (toolEv) {
			ctx.toolTracker.processEvent(toolEv)
			continue
		}

		const activityEv = parseRunActivityEvent({
			id: ev.id,
			type: ev.type,
			data: (ev.data ?? {}) as Record<string, unknown>,
			created_at: ev.created_at ?? undefined,
			message_id: ev.message_id ?? undefined,
		})
		if (activityEv) {
			ctx.processRunActivityEvent(activityEv)
			continue
		}

		const failure = parseRunFailureEvent({
			id: ev.id,
			type: ev.type,
			data: (ev.data ?? {}) as Record<string, unknown>,
			created_at: ev.created_at ?? undefined,
			message_id: ev.message_id ?? undefined,
		})
		if (failure) {
			ctx.recordRunFailure(failure)
			continue
		}

		// only events the backend anchored to a message reach this route at all,
		// so what lands here is exactly the system history that survives a reload.
		for (const systemEvent of parseChatSystemEvents({
			id: ev.id,
			type: ev.type,
			data: (ev.data ?? {}) as Record<string, unknown>,
			created_at: ev.created_at ?? undefined,
			message_id: ev.message_id ?? undefined,
			thread_id: ev.thread_id ?? undefined,
		})) {
			ctx.recordSystemEvent(systemEvent)
		}
	}
}

/**
 * fetch every event page for a chunk of message ids.
 *
 * one message can hold unboundedly many events, so a caller that reads only the
 * first page caches an incomplete set and the cache's "all covered" check then
 * short-circuits future loads against partial data.
 */
async function fetchAllEventPages(
	threadId: string,
	messageIds: string[],
	isCurrent: () => boolean
): Promise<ApiEvent[] | null> {
	const events: ApiEvent[] = []
	let cursor: string | null = null

	do {
		const { data, error }: { data?: ApiEventPage; error?: unknown } = await api.POST(
			'/v1/threads/{thread_id}/events/by-message-ids',
			{
				params: { path: { thread_id: threadId } },
				body: { message_ids: messageIds, limit: EVENT_PAGE_LIMIT, cursor },
			}
		)
		if (!isCurrent()) return null
		if (error || !data) return null

		events.push(...data.items)
		cursor = data.has_more ? (data.next_cursor ?? null) : null
	} while (cursor)

	return events
}

/** fetch and process message-scoped events for a batch of message ids */
export async function fetchEventsForThread(
	threadId: string,
	msgIds: string[],
	ctx: ChatContext,
	isCurrent: () => boolean = () => true
): Promise<void> {
	if (msgIds.length === 0) return
	if (!isCurrent()) return

	// check if the events cache covers all requested message IDs
	const cached = chatStore.threadCache.getCachedEvents(threadId)
	if (cached) {
		const allCovered = msgIds.every((id) => cached.messageIds.has(id))
		if (allCovered) {
			// replay from cache - skip the API entirely
			if (!isCurrent()) return
			replayEvents(cached.events, ctx)
			for (const id of msgIds) ctx.fetchedEventMessageIds.add(id)
			return
		}
	}

	// queue IDs that haven't been fetched yet
	for (const id of msgIds) {
		if (!ctx.fetchedEventMessageIds.has(id)) {
			ctx.eventMessageIdsPending.add(id)
		}
	}

	// if already fetching, the current fetch will pick up queued IDs on completion
	if (ctx.eventsInFlight) return

	// process all pending IDs
	while (ctx.eventMessageIdsPending.size > 0) {
		const pending = Array.from(ctx.eventMessageIdsPending)
		ctx.eventMessageIdsPending.clear()

		ctx.eventsInFlight = true
		try {
			for (let start = 0; start < pending.length; start += EVENT_MESSAGE_ID_CHUNK) {
				const batch = pending.slice(start, start + EVENT_MESSAGE_ID_CHUNK)
				const events = await fetchAllEventPages(threadId, batch, isCurrent)
				if (!isCurrent()) return
				if (events) {
					replayEvents(events, ctx)
					// re-read cache state each iteration to avoid stale closure
					const current = chatStore.threadCache.getCachedEvents(threadId)
					if (current) {
						chatStore.threadCache.appendEvents(threadId, events, batch)
					} else {
						chatStore.threadCache.setEvents(threadId, events, batch)
					}
				}
				for (const id of batch) ctx.fetchedEventMessageIds.add(id)
			}
		} finally {
			ctx.eventsInFlight = false
		}
	}
}

/** add messages to the tree and register any tool calls/results */
export function ingestMessages(msgs: ApiMessage[], ctx: ChatContext): void {
	for (const msg of msgs) {
		const steeringState = getMessageSteeringState(msg)
		if (msg.type === 'user' && steeringState === 'queued') {
			const runId = getMessageSteeringRunId(msg)
			if (runId) {
				ctx.stageQueuedSteeringMessage({
					id: msg.id,
					runId,
					content: msg.content,
					text: '',
					attachments: [],
					createdAt: getMessageCreatedAt(msg),
					message: msg,
				})
			}
			continue
		}
		if (msg.type === 'user' && steeringState === 'dropped') continue
		ctx.messageTree.set(msg.id, msg)
		if (msg.type === 'assistant') {
			for (const tc of parseToolCalls(msg)) ctx.toolTracker.registerToolCall(tc)
			if (msg.citations?.length) {
				ctx.citationSources.set(msg.id, msg.citations)
			}
		}
		if (msg.type === 'tool') {
			const result = parseToolResult(msg)
			if (result) {
				const refs = extractAttachmentRefs(msg)
				if (refs.length > 0) result.attachmentRefs = refs
				ctx.toolTracker.registerResult(result)
			}
		}
	}
}

/** load the next page of older messages (scroll-up pagination) */
export async function loadOlderMessages(threadId: string, ctx: ChatContext): Promise<void> {
	if (!ctx.scrollContainer) return
	if (ctx.isLoadingOlderMessages) return
	if (!ctx.hasMoreMessages) return

	ctx.isLoadingOlderMessages = true
	const prevScrollHeight = ctx.scrollContainer.scrollHeight
	const prevScrollTop = ctx.scrollContainer.scrollTop

	try {
		const cursor = ctx.branchCursorTowardRoot
		if (!cursor) {
			ctx.hasMoreMessages = false
			return
		}

		const { page: data, status } = await fetchBranchPage(threadId, { cursor })
		// 422 means the branch moved under the cursor (a canon switch, or the
		// boundary message being deleted). that is "reload from the top", not
		// a fatal error.
		if (status === 422) {
			ctx.branchCursorTowardRoot = null
			void loadTree(threadId, ctx, { anchorMessageId: ctx.currentLeafId })
			return
		}
		if (!data) return
		// guard against stale responses arriving after the user navigated away
		if (threadId !== ctx.thread?.id) return

		const page = data.messages
		absorbBranchPage(data, ctx, 'root')
		if (page.length === 0) return
		ctx.messageSkip += page.length
		ingestMessages(branchPageMessages(data), ctx)

		await fetchEventsForThread(
			threadId,
			page.map((m) => m.id),
			ctx,
			() => threadId === ctx.thread?.id
		)
		if (threadId !== ctx.thread?.id) return
		// rendered blocks are imperative state, not derived from the tree: without
		// this the page joins the tree and never reaches the screen.
		ctx.rebuildRunBlocks()

		await tick()
		// guard again: component may have unmounted during awaits
		if (!ctx.scrollContainer || threadId !== ctx.thread?.id) return
		const newScrollHeight = ctx.scrollContainer.scrollHeight
		// this scrollTop write fires a scroll event near the top; suppress it so
		// it isn't misread as a user scroll that flips the auto-scroll pin.
		ctx.markProgrammaticScroll('auto')
		ctx.scrollContainer.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight)
	} finally {
		ctx.isLoadingOlderMessages = false
	}
}

/**
 * load the next page of newer messages (scroll-down pagination).
 *
 * a thread opened at the user's last-read message starts mid-branch, so the
 * tail is reached by paging down. the new page hangs off the loaded window's
 * leaf, so the leaf pointer follows it - otherwise the branch walk stops where
 * the window used to end and the page renders nothing new.
 */
export async function loadNewerMessages(threadId: string, ctx: ChatContext): Promise<void> {
	if (ctx.isLoadingNewerMessages) return
	if (!ctx.hasNewerMessages) return

	ctx.isLoadingNewerMessages = true
	try {
		const cursor = ctx.branchCursorTowardLeaf
		if (!cursor) {
			ctx.hasNewerMessages = false
			return
		}

		const leafBefore = ctx.currentLeafId
		const { page: data, status } = await fetchBranchPage(threadId, { cursor })
		// same cursor contract as scrolling up: a 422 means the branch moved
		// under it, which is "reload this thread", not a fatal error.
		if (status === 422) {
			ctx.branchCursorTowardLeaf = null
			ctx.hasNewerMessages = false
			void loadTree(threadId, ctx, { anchorMessageId: ctx.currentLeafId })
			return
		}
		if (!data) return
		if (threadId !== ctx.thread?.id) return

		const page = data.messages
		absorbBranchPage(data, ctx, 'leaf')
		if (page.length === 0) return
		ingestMessages(branchPageMessages(data), ctx)

		// follow the branch down unless the user moved off it meanwhile
		const newLeaf = page[page.length - 1].id
		if (ctx.currentLeafId === leafBefore && ctx.messageTree.has(newLeaf)) {
			ctx.currentLeafId = newLeaf
		}

		await fetchEventsForThread(
			threadId,
			page.map((m) => m.id),
			ctx,
			() => threadId === ctx.thread?.id
		)
		if (threadId !== ctx.thread?.id) return
		ctx.rebuildRunBlocks()
		await tick()
		if (threadId !== ctx.thread?.id) return
		// the page landing reflows the transcript, and a shrink clamps scrollTop
		// for us. suppress that scroll so it is not read as the reader arriving
		// at the opposite edge, which would page straight back the other way.
		ctx.markProgrammaticScroll('auto')
		ctx.measureScrollable()
	} finally {
		ctx.isLoadingNewerMessages = false
	}
}

/**
 * the caller's own per-thread state (read cursor, mute / pin / archive).
 *
 * the API exposes no GET for it: the roster carries membership only, and thread
 * payloads no longer inline it. a PATCH with no fields changes nothing and
 * answers with the current row, which is the only read available today.
 */
async function fetchThreadUserState(threadId: string): Promise<ThreadUserState | null> {
	const userId = session.currentUserId
	if (!userId) return null
	const { data, error } = await api.PATCH(
		'/v1/threads/{thread_id}/participants/users/{user_id}',
		{
			params: { path: { thread_id: threadId, user_id: userId } },
			body: {},
		}
	)
	if (error || !data) return null
	return data
}

/**
 * the message a thread should open at, or null for the live tail.
 *
 * a reader who is caught up gets the tail, which is the page they would have
 * been given anyway - no anchor, no second request path.
 */
function lastReadAnchor(state: ThreadUserState | null, thread: Thread): string | null {
	const lastRead = state?.last_read_message_id ?? null
	if (!lastRead || lastRead === thread.current_message_id) return null
	return lastRead
}

/**
 * load the selected branch page for a thread.
 *
 * without options the page opens where the user left off: their last-read
 * message anchors the request and paging then runs in both directions from
 * there. pass an explicit anchor (or null for the live tail) to override that.
 */
export async function loadTree(
	threadId: string,
	ctx: ChatContext,
	options?: LoadTreeOptions
): Promise<boolean> {
	const loadToken = ctx.beginThreadLoad(threadId)
	const isCurrent = () => ctx.isThreadLoadCurrent(threadId, loadToken)

	// a sidebar hover may still be filling the cache for this thread; racing it
	// fetches the same thread and branch page twice.
	await chatStore.threadCache.awaitPrefetch(threadId)
	if (!isCurrent()) return false

	// try cache first for instant load
	const cachedThread = chatStore.threadCache.get(threadId)
	const cachedMessages = chatStore.threadCache.getCachedMessageSnapshot(threadId)
	const cachedLeaf = cachedThread?.current_message_id ?? null
	const cacheHasSelectedLeaf =
		cachedLeaf === null || chatStore.threadCache.hasCachedMessage(threadId, cachedLeaf)

	let threadData: Thread
	let messagesPage: ApiMessage[]
	let pageSize: number
	let complete: boolean
	let anchorMessageId: string | null = null

	if (cachedThread && cachedMessages && cacheHasSelectedLeaf) {
		// use cached data for instant render
		threadData = cachedThread
		messagesPage = cachedMessages.messages
		pageSize = cachedMessages.pageSize
		complete = cachedMessages.complete
		if (cachedMessages.branch) {
			absorbBranchPaging(cachedMessages.branch, ctx, 'both')
		} else {
			ctx.branchCursorTowardRoot = null
			ctx.branchCursorTowardLeaf = null
			ctx.hasNewerMessages = false
		}
	} else {
		// fetch from api. capture timestamp before the request so any
		// message.* event arriving during the fetch will invalidate this
		// (potentially partial) result via setMessages's race guard.
		const fetchStartedAt = Date.now()
		// the user-state read needs only the ids, so it rides alongside the thread
		// request instead of queueing behind it; only the anchor comparison below
		// needs the thread payload. it is caught so a thread failure still
		// surfaces exactly as it did when this ran second.
		const userStatePromise = options ? null : fetchThreadUserState(threadId).catch(() => null)
		const [{ data, error: threadError, response: threadResponse }, userState] =
			await Promise.all([
				api.GET('/v1/threads/{thread_id}', {
					params: { path: { thread_id: threadId } },
				}),
				userStatePromise,
			])
		if (!isCurrent()) return false
		if (threadError) {
			if (threadResponse?.status === 404) throw new ThreadNotFoundError(threadId)
			console.error('failed to load thread', threadError)
			ctx.thread = null
			chatStore.activeThread = null
			ctx.toolTracker.clear()
			ctx.messageTree.clear()
			ctx.currentLeafId = null
			ctx.rebuildRunBlocks()
			return false
		}
		if (!data) {
			ctx.thread = null
			chatStore.activeThread = null
			ctx.toolTracker.clear()
			ctx.messageTree.clear()
			ctx.currentLeafId = null
			ctx.rebuildRunBlocks()
			throw new ThreadNotFoundError(threadId)
		}
		threadData = data

		anchorMessageId = options ? options.anchorMessageId : lastReadAnchor(userState, threadData)

		// the branch page is the ONE message-loading path: it carries the
		// chain plus the branches hanging off it, so `/messages` (a flat,
		// branch-blind list) is no longer part of chat rendering.
		let branchRes = await fetchBranchPage(threadId, anchorMessageId ? { anchorMessageId } : {})
		if (!isCurrent()) return false
		// an anchor the thread cannot page - deleted, or a branch abandoned
		// before the thread was shared - 404s. the live tail always loads.
		if (!branchRes.page && anchorMessageId) {
			anchorMessageId = null
			branchRes = await fetchBranchPage(threadId)
			if (!isCurrent()) return false
		}

		if (!branchRes.page) {
			console.error('failed to load current branch', branchRes.status)
			ctx.currentLeafId = null
			ctx.messageSkip = 0
			ctx.hasMoreMessages = true
			return false
		}

		const branchPage = branchRes.page
		const paging = branchPagingOf(branchPage)
		absorbBranchPaging(paging, ctx, 'both')
		messagesPage = branchPageMessages(branchPage)
		pageSize = branchPage.messages.length
		complete = !branchPage.has_toward_root

		// cache for future instant loads (race guard: dropped if a
		// message.* event arrived since fetchStartedAt).
		chatStore.threadCache.set(threadData)
		chatStore.threadCache.setMessages(
			threadId,
			messagesPage,
			complete,
			fetchStartedAt,
			pageSize,
			paging
		)
	}

	if (!isCurrent()) return false

	ctx.thread = threadData
	chatStore.activeThread = threadData

	// mark thread as read when the user opens it
	void chatStore.markThreadRead(threadId)

	ctx.messageTree.clear()
	ctx.messageSkip = pageSize
	ctx.hasMoreMessages = !complete
	ingestMessages(messagesPage, ctx)

	const preferredLeaf = threadData.current_message_id
	if (preferredLeaf && ctx.messageTree.has(preferredLeaf)) {
		ctx.currentLeafId = preferredLeaf
	} else if (ctx.messageTree.size > 0) {
		let latest: ApiMessage | null = null
		for (const msg of ctx.messageTree.values()) {
			if (!latest) {
				latest = msg
				continue
			}
			if (getMessageCreatedAt(msg).getTime() >= getMessageCreatedAt(latest).getTime()) {
				latest = msg
			}
		}
		ctx.currentLeafId = latest?.id ?? null
	} else {
		ctx.currentLeafId = null
	}

	// the view is parked on the anchor, so the page reveals it instead of
	// pinning to the bottom. the pin stays off until the tail is actually
	// loaded, or every downward page would drag the reader to the next one.
	ctx.initialAnchorMessageId = anchorMessageId
	if (ctx.hasNewerMessages) ctx.autoScroll = false

	await fetchEventsForThread(
		threadId,
		Array.from(ctx.messageTree.values()).map((m) => m.id),
		ctx,
		isCurrent
	)
	if (!isCurrent()) return false
	// safety net: any tool calls still pending/running after load are
	// orphans from an interrupted run. close them so we don't render
	// permanent shimmer - UNLESS a run is still active for this thread, in
	// which case the resume stream owns those tool calls and they must keep
	// shimmering until a tool result actually arrives. closing them here
	// would make an in-flight tool look completed (registerToolCall on
	// resume does not reset status, and registerResult only fires on real
	// completion). only confirm with the backend when we actually have open
	// tool calls but the store has no run yet (avoids the common-case fetch).
	if (ctx.toolTracker.hasActive && !activeRunsStore.hasActiveRuns(threadId)) {
		await activeRunsStore.refresh()
		if (!isCurrent()) return false
	}
	if (!activeRunsStore.hasActiveRuns(threadId)) {
		ctx.toolTracker.closeAllActive()
	}
	ctx.rebuildRunBlocks()
	return true
}

/**
 * sync the current in-memory message tree and leaf pointer back to the
 * thread cache so navigating away and back renders all messages.
 */
export function syncCacheAfterRun(ctx: ChatContext): void {
	if (!ctx.thread) return
	// update cached thread's current_message_id to the live leaf
	const updatedThread = { ...ctx.thread, current_message_id: ctx.currentLeafId ?? null }
	chatStore.threadCache.set(updatedThread)
	// write all in-memory messages back to cache
	const allMessages = Array.from(ctx.messageTree.values())
	chatStore.threadCache.setMessages(
		ctx.thread.id,
		allMessages,
		!ctx.hasMoreMessages,
		undefined,
		ctx.messageSkip,
		{
			cursorTowardRoot: ctx.branchCursorTowardRoot,
			cursorTowardLeaf: ctx.branchCursorTowardLeaf,
			hasTowardRoot: ctx.hasMoreMessages,
			hasTowardLeaf: ctx.hasNewerMessages,
			siblingCounts: Array.from(ctx.siblingCounts.entries()),
		}
	)
	// register new message IDs as covered so events cache stays valid.
	// events from the run arrived via SSE (already processed by toolTracker),
	// so we just mark the message IDs as covered without invalidating.
	chatStore.threadCache.addCoveredMessageIds(
		ctx.thread.id,
		allMessages.map((m) => m.id)
	)
}

type AccessLevel = components['schemas']['AccessLevel']

/**
 * fetch the requester's effective access level on a thread.
 * returns the level string, or null if the request fails.
 */
export async function fetchThreadAccessLevel(threadId: string): Promise<AccessLevel | null> {
	const userId = session.currentUserId
	if (!userId) return null
	const results = await resolveResourceAccessLevels('thread', threadId, [userId])
	return results.find((result) => result.user_id === userId)?.level ?? null
}
