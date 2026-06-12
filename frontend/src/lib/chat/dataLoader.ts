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
import { extractAttachmentRefs, getMessageCreatedAt, type ApiMessage } from './helpers'
import { parseRunActivityEvent } from './runActivities'
import { getMessageSteeringRunId, getMessageSteeringState } from './steering'
import type { ChatContext } from './types'

type ApiEvent = components['schemas']['Event']
const INITIAL_MESSAGE_LIMIT = 120

export class ThreadNotFoundError extends Error {
	constructor(threadId: string) {
		super(`thread not found: ${threadId}`)
		this.name = 'ThreadNotFoundError'
	}
}

function mergeMessages(...groups: ApiMessage[][]): ApiMessage[] {
	const byId = new Map<string, ApiMessage>()
	for (const group of groups) {
		for (const msg of group) byId.set(msg.id, msg)
	}
	return Array.from(byId.values())
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
	}
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
		const batch = Array.from(ctx.eventMessageIdsPending)
		ctx.eventMessageIdsPending.clear()

		ctx.eventsInFlight = true
		try {
			const { data, error } = await api.POST(
				'/v1/threads/{thread_id}/events/by-message-ids',
				{
					params: { path: { thread_id: threadId } },
					body: { message_ids: batch },
				}
			)
			if (!isCurrent()) return
			if (!error && data) {
				const events = data as ApiEvent[]
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
		const { data, error } = await api.GET('/v1/threads/{thread_id}/messages', {
			params: {
				path: { thread_id: threadId },
				query: { skip: ctx.messageSkip, limit: 120 },
			},
		})
		if (error) return
		// guard against stale responses arriving after the user navigated away
		if (threadId !== ctx.thread?.id) return
		const page = (data ?? []) as ApiMessage[]
		if (page.length === 0) {
			ctx.hasMoreMessages = false
			return
		}
		ctx.messageSkip += page.length
		ingestMessages(page, ctx)

		await fetchEventsForThread(
			threadId,
			page.map((m) => m.id),
			ctx,
			() => threadId === ctx.thread?.id
		)

		await tick()
		// guard again: component may have unmounted during awaits
		if (!ctx.scrollContainer || threadId !== ctx.thread?.id) return
		const newScrollHeight = ctx.scrollContainer.scrollHeight
		ctx.scrollContainer.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight)
	} finally {
		ctx.isLoadingOlderMessages = false
	}
}

/** load the selected branch plus the latest paginated message page for a thread. */
export async function loadTree(threadId: string, ctx: ChatContext): Promise<boolean> {
	const loadToken = ctx.beginThreadLoad(threadId)
	const isCurrent = () => ctx.isThreadLoadCurrent(threadId, loadToken)

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

	if (cachedThread && cachedMessages && cacheHasSelectedLeaf) {
		// use cached data for instant render
		threadData = cachedThread
		messagesPage = cachedMessages.messages
		pageSize = cachedMessages.pageSize
		complete = cachedMessages.complete
	} else {
		// fetch from api. capture timestamp before the request so any
		// message.* event arriving during the fetch will invalidate this
		// (potentially partial) result via setMessages's race guard.
		const fetchStartedAt = Date.now()
		const {
			data,
			error: threadError,
			response: threadResponse,
		} = await api.GET('/v1/threads/{thread_id}', {
			params: { path: { thread_id: threadId } },
		})
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

		const [messagesRes, branchRes] = await Promise.all([
			api.GET('/v1/threads/{thread_id}/messages', {
				params: {
					path: { thread_id: threadId },
					query: { skip: 0, limit: INITIAL_MESSAGE_LIMIT },
				},
			}),
			threadData.current_message_id
				? api.GET('/v1/threads/{thread_id}/branch', {
						params: { path: { thread_id: threadId } },
					})
				: Promise.resolve({ data: [] as ApiMessage[], error: undefined }),
		])
		if (!isCurrent()) return false

		const { data: msgData, error: msgError } = messagesRes
		if (msgError) {
			console.error('failed to load messages', msgError)
			ctx.currentLeafId = null
			ctx.messageSkip = 0
			ctx.hasMoreMessages = true
			return false
		}

		if (branchRes.error) {
			console.error('failed to load current branch', branchRes.error)
		}

		const latestPage = (msgData ?? []) as ApiMessage[]
		const selectedBranch = ((branchRes.data ?? []) as ApiMessage[]).filter(
			(msg) => msg.thread_id === threadId
		)
		messagesPage = mergeMessages(latestPage, selectedBranch)
		pageSize = latestPage.length
		complete = latestPage.length < INITIAL_MESSAGE_LIMIT

		// cache for future instant loads (race guard: dropped if a
		// message.* event arrived since fetchStartedAt).
		chatStore.threadCache.set(threadData)
		chatStore.threadCache.setMessages(
			threadId,
			messagesPage,
			complete,
			fetchStartedAt,
			pageSize
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
		ctx.messageSkip
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
