/**
 * thread-level API actions - delete and rename/tag update.
 * these operations act on the thread list in the chat store, not on a per-page ChatContext.
 */

import { api } from '$lib/api/client'
import { chat } from '$lib/stores/chat.svelte'
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
