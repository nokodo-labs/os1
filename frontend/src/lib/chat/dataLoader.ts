/**
 * data loading - tool events, message ingestion, pagination, tree loading, cache sync.
 */

import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { chat as chatStore } from '$lib/stores/chat.svelte'
import { parseToolCalls, parseToolEvent, parseToolResult } from '$lib/tools'
import { tick } from 'svelte'
import { getMessageCreatedAt, type ApiMessage } from './helpers'
import type { ChatContext } from './types'

type ApiEvent = components['schemas']['Event']

/** fetch and process tool events for a batch of message ids */
export async function fetchToolEventsForThread(
	threadId: string,
	msgIds: string[],
	ctx: ChatContext
): Promise<void> {
	if (msgIds.length === 0) return

	// queue IDs that haven't been fetched yet
	for (const id of msgIds) {
		if (!ctx.fetchedToolEventMessageIds.has(id)) {
			ctx.toolEventsPendingIds.add(id)
		}
	}

	// if already fetching, the current fetch will pick up queued IDs on completion
	if (ctx.toolEventsInFlight) return

	// process all pending IDs
	while (ctx.toolEventsPendingIds.size > 0) {
		const batch = Array.from(ctx.toolEventsPendingIds)
		ctx.toolEventsPendingIds.clear()

		ctx.toolEventsInFlight = true
		try {
			const { data, error } = await apiClient().POST(
				'/v1/threads/{thread_id}/events/by-message-ids',
				{
					params: { path: { thread_id: threadId } },
					body: { message_ids: batch },
				}
			)
			if (!error && data) {
				for (const ev of data as ApiEvent[]) {
					const toolEv = parseToolEvent({
						id: ev.id,
						type: ev.type,
						data: (ev.data ?? {}) as Record<string, unknown>,
						created_at: ev.created_at ?? undefined,
						message_id: ev.message_id ?? undefined,
					})
					if (toolEv) ctx.toolTracker.processEvent(toolEv)
				}
			}
			for (const id of batch) ctx.fetchedToolEventMessageIds.add(id)
		} finally {
			ctx.toolEventsInFlight = false
		}
	}
}

/** add messages to the tree and register any tool calls/results */
export function ingestMessages(msgs: ApiMessage[], ctx: ChatContext): void {
	for (const msg of msgs) {
		ctx.messageTree.set(msg.id, msg)
		if (msg.type === 'assistant') {
			for (const tc of parseToolCalls(msg)) ctx.toolTracker.registerToolCall(tc)
		}
		if (msg.type === 'tool') {
			const result = parseToolResult(msg)
			if (result) ctx.toolTracker.registerResult(result)
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
		const { data, error } = await apiClient().GET('/v1/threads/{thread_id}/messages', {
			params: {
				path: { thread_id: threadId },
				query: { skip: ctx.messageSkip, limit: 120 },
			},
		})
		if (error) return
		const page = (data ?? []) as ApiMessage[]
		if (page.length === 0) {
			ctx.hasMoreMessages = false
			return
		}
		ctx.messageSkip += page.length
		ingestMessages(page, ctx)

		await fetchToolEventsForThread(
			threadId,
			page.filter((m) => m.type === 'assistant').map((m) => m.id),
			ctx
		)

		await tick()
		const newScrollHeight = ctx.scrollContainer.scrollHeight
		ctx.scrollContainer.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight)
	} finally {
		ctx.isLoadingOlderMessages = false
	}
}

/** load the full message tree for a thread (with cache-first strategy) */
export async function loadTree(threadId: string, ctx: ChatContext): Promise<boolean> {
	// try cache first for instant load
	const cachedThread = chatStore.threadCache.get(threadId)
	const cachedMessages = chatStore.threadCache.getCachedMessages(threadId)

	let threadData: typeof cachedThread
	let messagesPage: ApiMessage[]

	if (cachedThread && cachedMessages) {
		// use cached data for instant render
		threadData = cachedThread
		messagesPage = cachedMessages
	} else {
		// fetch from API
		const { data, error: threadError } = await apiClient().GET('/v1/threads/{thread_id}', {
			params: { path: { thread_id: threadId } },
		})
		if (threadError) {
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
			return true
		}
		threadData = data

		const { data: msgData, error: msgError } = await apiClient().GET(
			'/v1/threads/{thread_id}/messages',
			{ params: { path: { thread_id: threadId }, query: { skip: 0, limit: 120 } } }
		)
		if (msgError) {
			console.error('failed to load messages', msgError)
			ctx.currentLeafId = null
			return false
		}
		messagesPage = (msgData ?? []) as ApiMessage[]

		// cache for future instant loads
		chatStore.threadCache.set(threadData)
		chatStore.threadCache.setMessages(threadId, messagesPage, messagesPage.length < 120)
	}

	ctx.thread = threadData
	chatStore.activeThread = threadData

	ctx.toolTracker.clear()
	ctx.messageTree.clear()
	ctx.messageSkip = messagesPage.length
	// more messages exist if we got a full page (limit is 120)
	ctx.hasMoreMessages = messagesPage.length >= 120
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

	await fetchToolEventsForThread(
		threadId,
		Array.from(ctx.messageTree.values())
			.filter((m) => m.type === 'assistant')
			.map((m) => m.id),
		ctx
	)
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
	chatStore.threadCache.setMessages(ctx.thread.id, allMessages, !ctx.hasMoreMessages)
}
