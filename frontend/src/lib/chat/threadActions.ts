/**
 * thread-level API actions - delete, rename/tag update, and SSE event handling.
 * these operations act on the thread list in the chat store, not on a per-page ChatContext.
 */

import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import { chat, type Thread } from '$lib/stores/chat.svelte'
import { showError } from '$lib/stores/notifications.svelte'

/** delete a thread via API. returns the HTTP status, or null on network error. */
export async function deleteThread(threadId: string): Promise<number | null> {
	const { response } = await api.DELETE('/v1/threads/{thread_id}', {
		params: { path: { thread_id: threadId } },
	})
	return response.status
}

/**
 * update a thread's title and tags with optimistic update + rollback.
 * returns true on success, false on error (also calls showError).
 */
export async function updateThread(
	threadId: string,
	title: string,
	tags: string[]
): Promise<boolean> {
	const prevThread = chat.recentThreads.find((t) => t.id === threadId)

	// optimistic update
	chat.updateRecentThread(threadId, (thread) => ({
		...thread,
		title: title || thread.title,
		tags,
	}))

	try {
		const { error } = await api.PATCH('/v1/threads/{thread_id}', {
			params: { path: { thread_id: threadId } },
			body: { title: title || undefined, tags },
		})

		if (error) {
			if (prevThread) chat.updateRecentThread(threadId, () => prevThread)
			showError('could not save changes')
			return false
		}

		return true
	} catch {
		if (prevThread) chat.updateRecentThread(threadId, () => prevThread)
		showError('could not save changes')
		return false
	}
}

/**
 * handle a real-time thread SSE event.
 * @param event - the stream message received
 * @param currentPathname - current window pathname, used to decide whether to navigate away
 * @param onNavigateAway - called with the target path when we need to redirect (e.g. thread was deleted)
 */
export function handleThreadStreamEvent(
	event: StreamMessage,
	currentPathname: string,
	onNavigateAway: (path: '/') => void
): void {
	const eventType = event.type
	const data = event.data as Record<string, unknown> | undefined
	const threadId = (data?.thread_id as string) || (event.thread_id as string) || ''

	const patch = (data?.patch ?? null) as { title?: unknown; tags?: unknown } | null

	if (eventType === 'thread.deleted' && threadId) {
		chat.threadCache.invalidateAll(threadId)
		chat.removeRecentThread(threadId)
		if (currentPathname === `/c/${threadId}`) {
			onNavigateAway('/')
		}
	} else if (eventType === 'thread.updated' && threadId) {
		chat.threadCache.invalidateAll(threadId)

		const rawTitle =
			(typeof patch?.title === 'string' ? patch.title : null) ??
			(typeof data?.title === 'string' ? data.title : null)
		const rawTags =
			(Array.isArray(patch?.tags) ? patch.tags : null) ??
			(Array.isArray(data?.tags) ? data.tags : null)

		chat.updateRecentThread(threadId, (thread: Thread) => {
			const nextTags = rawTags
				? rawTags.filter((t): t is string => typeof t === 'string')
				: null
			return {
				...thread,
				title: rawTitle ?? thread.title,
				tags: nextTags ?? thread.tags,
				last_activity_at: new Date().toISOString(),
			}
		})
	} else if (eventType === 'thread.created') {
		// handled by chat.svelte.ts#handleStreamEvent which immediately
		// prepends the new thread to recentThreads. no async refresh
		// needed here - it would race and overwrite the list.
	}
}
