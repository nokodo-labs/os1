/**
 * conversation search for the messages app.
 *
 * two sources, because neither answers a search here on its own:
 *
 * - the listed inbox matches on the name a row actually shows. a DM carries no
 *   title of its own, so the person's name exists only on the client side.
 * - `/v1/threads/search` (the endpoint project-scoped search already uses)
 *   matches titles, tags and message content, scoped to people threads.
 *
 * a search hit is a scalar thread: that payload never carries the roster, which
 * is what names a DM and draws its faces. a hit is therefore kept only when it
 * can be matched back to a thread already held - the inbox itself or the thread
 * cache - and dropped otherwise, rather than drawn as an anonymous group.
 */

import { api } from '$lib/api/client'
import { chat, type Thread } from '$lib/stores/chat.svelte'
import { conversationDisplay } from '$lib/utils/conversationDisplay'

const DEFAULT_LIMIT = 20

export interface ConversationSearchOptions {
	query: string
	userId: string
	/** conversations already listed; matched here on the name their rows show. */
	loaded: readonly Thread[]
	limit?: number
	signal?: AbortSignal
}

/** does this conversation read as the one being looked for, by name? */
export function conversationMatchesName(
	thread: Thread,
	query: string,
	userId: string | null
): boolean {
	const needle = query.trim().toLowerCase()
	if (!needle) return false
	const haystack = `${thread.title ?? ''} ${conversationDisplay(thread, userId).title}`
	return haystack.toLowerCase().includes(needle)
}

/** pending requests are held in full client-side, so they need no server pass. */
export function searchInvites(
	invites: readonly Thread[],
	query: string,
	userId: string | null
): Thread[] {
	return invites.filter((invite) => conversationMatchesName(invite, query, userId))
}

/** local name matches first, then the server's title/content hits it did not already list. */
export async function searchConversations(options: ConversationSearchOptions): Promise<Thread[]> {
	const query = options.query.trim()
	if (!query) return []

	const found = options.loaded.filter((thread) =>
		conversationMatchesName(thread, query, options.userId)
	)
	const seen = new Set(found.map((thread) => thread.id))

	const { data } = await api.GET('/v1/threads/search', {
		params: {
			query: {
				q: query,
				limit: options.limit ?? DEFAULT_LIMIT,
				participant_scope: 'people',
				not_archived_by: options.userId,
				not_invite_pending_for: options.userId,
			},
		},
		signal: options.signal,
	})

	for (const hit of data?.items ?? []) {
		if (seen.has(hit.id)) continue
		const known = chat.threadCache.get(hit.id)
		if (!known) continue
		seen.add(hit.id)
		found.push(known)
	}

	return found
}
