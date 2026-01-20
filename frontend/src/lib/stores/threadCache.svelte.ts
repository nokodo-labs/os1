/**
 * Thread cache store for prefetching and caching thread metadata and messages.
 * Provides:
 * - Thread metadata cache with invalidation on SSE events
 * - Message cache per thread (with pagination support)
 * - Hover-triggered prefetch for instant page loads
 */

import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

type ApiThread = components['schemas']['Thread']
type ApiMessage = components['schemas']['Message']

// cache TTL in milliseconds
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

interface ThreadCacheEntry {
	thread: ApiThread
	fetchedAt: number
}

interface MessageCacheEntry {
	messages: ApiMessage[]
	fetchedAt: number
	complete: boolean // true if all messages loaded
}

// reactive state using Svelte 5 runes
const threadCache = new SvelteMap<string, ThreadCacheEntry>()
const messageCache = new SvelteMap<string, MessageCacheEntry>()
const prefetchInFlight = new SvelteSet<string>()

/**
 * Check if a cache entry is still valid (not expired)
 */
function isFresh(fetchedAt: number): boolean {
	return Date.now() - fetchedAt < CACHE_TTL_MS
}

/**
 * Get cached thread metadata if fresh
 */
export function getCachedThread(threadId: string): ApiThread | null {
	const entry = threadCache.get(threadId)
	if (!entry || !isFresh(entry.fetchedAt)) return null
	return entry.thread
}

/**
 * Get cached messages if fresh
 */
export function getCachedMessages(threadId: string): ApiMessage[] | null {
	const entry = messageCache.get(threadId)
	if (!entry || !isFresh(entry.fetchedAt)) return null
	return entry.messages
}

/**
 * Store thread in cache
 */
export function cacheThread(thread: ApiThread): void {
	threadCache.set(thread.id, {
		thread,
		fetchedAt: Date.now(),
	})
}

/**
 * Store messages in cache
 */
export function cacheMessages(
	threadId: string,
	messages: ApiMessage[],
	complete: boolean = false
): void {
	messageCache.set(threadId, {
		messages,
		fetchedAt: Date.now(),
		complete,
	})
}

/**
 * Invalidate thread cache (call on SSE thread.updated/thread.deleted)
 */
export function invalidateThread(threadId: string): void {
	threadCache.delete(threadId)
}

/**
 * Invalidate message cache (call on SSE message changes)
 */
export function invalidateMessages(threadId: string): void {
	messageCache.delete(threadId)
}

/**
 * Invalidate all caches for a thread
 */
export function invalidateAll(threadId: string): void {
	threadCache.delete(threadId)
	messageCache.delete(threadId)
}

/**
 * Clear entire cache
 */
export function clearCache(): void {
	threadCache.clear()
	messageCache.clear()
	prefetchInFlight.clear()
}

/**
 * Prefetch thread metadata and initial messages on hover.
 * Non-blocking; won't refetch if already cached and fresh.
 */
export async function prefetchThread(threadId: string): Promise<void> {
	// skip if already cached and fresh
	if (getCachedThread(threadId) && getCachedMessages(threadId)) return

	// skip if prefetch already in flight
	if (prefetchInFlight.has(threadId)) return
	prefetchInFlight.add(threadId)

	try {
		// fetch thread and messages in parallel
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

		if (threadRes.data) {
			cacheThread(threadRes.data)
		}
		if (messagesRes.data) {
			cacheMessages(threadId, messagesRes.data, messagesRes.data.length < 120)
		}
	} catch {
		// prefetch failures are silent - they're opportunistic
	} finally {
		prefetchInFlight.delete(threadId)
	}
}

/**
 * Get thread from cache or fetch.
 * Returns cached data immediately if available.
 */
export async function getThread(threadId: string): Promise<ApiThread | null> {
	const cached = getCachedThread(threadId)
	if (cached) return cached

	const { data, error } = await apiClient().GET('/v1/threads/{thread_id}', {
		params: { path: { thread_id: threadId } },
	})
	if (error || !data) return null

	cacheThread(data)
	return data
}

/**
 * Get messages from cache or fetch.
 * Returns { messages, fromCache } so caller knows if it needs to fetch more.
 */
export async function getMessages(
	threadId: string,
	skip: number = 0,
	limit: number = 120
): Promise<{ messages: ApiMessage[]; fromCache: boolean }> {
	// only serve from cache if skip=0 (initial load)
	if (skip === 0) {
		const cached = getCachedMessages(threadId)
		if (cached) return { messages: cached, fromCache: true }
	}

	const { data, error } = await apiClient().GET('/v1/threads/{thread_id}/messages', {
		params: {
			path: { thread_id: threadId },
			query: { skip, limit },
		},
	})
	if (error || !data) return { messages: [], fromCache: false }

	// only cache the initial page
	if (skip === 0) {
		cacheMessages(threadId, data, data.length < limit)
	}

	return { messages: data, fromCache: false }
}

/**
 * Check if prefetch is in progress for a thread
 */
export function isPrefetching(threadId: string): boolean {
	return prefetchInFlight.has(threadId)
}
