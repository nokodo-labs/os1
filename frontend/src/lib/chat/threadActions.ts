/**
 * thread-level API actions - delete and rename/tag update.
 * these operations act on the thread list in the chat store, not on a per-page ChatContext.
 */

import { api } from '$lib/api/client'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken } from '$lib/auth/session.svelte'
import type { DeleteOriginatedOptions } from '$lib/chat/types'
import { chat } from '$lib/stores/chat.svelte'
import type { ConfirmDeleteToggle } from '$lib/stores/modals.svelte'
import { showError } from '$lib/stores/notifications.svelte'

/** opt-in switch offered when confirming a thread delete. */
export const THREAD_ORIGINATED_TOGGLE: ConfirmDeleteToggle = {
	label: 'also delete what was created here',
	description:
		'notes, reminders, files and events created in this chat get deleted too. anything only attached to it is kept.',
}

/** delete a thread via API. returns the HTTP status, or null on network error. */
export async function deleteThread(
	threadId: string,
	options: DeleteOriginatedOptions = {}
): Promise<number | null> {
	const { response } = await api.DELETE('/v1/threads/{thread_id}', {
		params: {
			path: { thread_id: threadId },
			query: options.deleteOriginatedResources
				? { delete_originated_resources: true }
				: undefined,
		},
	})
	return response.status
}

/** archive state is per-user, so every write is addressed to the caller's participant row. */
async function setArchived(threadId: string, archived: boolean): Promise<boolean> {
	const token = getAccessToken()
	const userId = token ? getJwtUserId(token) : null
	if (!userId) return false

	const { error } = await api.PATCH('/v1/threads/{thread_id}/participants/users/{user_id}', {
		params: { path: { thread_id: threadId, user_id: userId } },
		body: { archived },
	})
	return !error
}

/** archive a thread for the current user (per-user state) with optimistic removal. */
export async function archiveThread(threadId: string): Promise<boolean> {
	const previousThread = chat.recentThreads.find((thread) => thread.id === threadId) ?? null
	if (previousThread) chat.removeRecentThread(threadId)

	try {
		if (!(await setArchived(threadId, true))) {
			if (previousThread) chat.recentThreads = [previousThread, ...chat.recentThreads]
			showError('could not archive chat')
			return false
		}

		void chat.refreshThreads()
		return true
	} catch {
		if (previousThread) chat.recentThreads = [previousThread, ...chat.recentThreads]
		showError('could not archive chat')
		return false
	}
}

/** unarchive a thread for the current user (per-user state). */
export async function unarchiveThread(threadId: string): Promise<boolean> {
	try {
		if (!(await setArchived(threadId, false))) {
			showError('could not unarchive chat')
			return false
		}

		void chat.refreshThreads()
		return true
	} catch {
		showError('could not unarchive chat')
		return false
	}
}

/**
 * mute or unmute a thread for the current user (per-user state).
 * returns the resulting flag, or null when the write failed.
 */
export async function setThreadMuted(threadId: string, muted: boolean): Promise<boolean | null> {
	const token = getAccessToken()
	const userId = token ? getJwtUserId(token) : null
	if (!userId) return null

	try {
		const { data, error } = await api.PATCH(
			'/v1/threads/{thread_id}/participants/users/{user_id}',
			{
				params: { path: { thread_id: threadId, user_id: userId } },
				body: { muted },
			}
		)
		if (error || !data) {
			showError(muted ? 'could not mute chat' : 'could not unmute chat')
			return null
		}
		return data.muted
	} catch {
		showError(muted ? 'could not mute chat' : 'could not unmute chat')
		return null
	}
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
