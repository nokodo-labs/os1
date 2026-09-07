/**
 * message-author identity, resolved client-side.
 *
 * a message carries only `sender_user_id` / `sender_agent_id`. the thread's
 * participant roster is what turns those ids into a name and avatar, so
 * identity is derived from the thread rather than duplicated onto every row.
 */

import type { Thread } from '$lib/stores/chat.svelte'
import type { ConversationFace } from '$lib/utils/conversationDisplay'
import { userDisplayName } from '$lib/utils/resourceAuthors'
import type { ApiMessage } from './types'

export interface MessageAuthor {
	id: string
	name: string
	avatarUrl: string | null
	isAgent: boolean
}

/** index a thread's human participants by user id. */
export function buildParticipantIndex(thread: Thread | null): Map<string, MessageAuthor> {
	const index = new Map<string, MessageAuthor>()
	for (const participant of thread?.participants ?? []) {
		if (participant.kind !== 'user') continue
		const user = participant.user
		index.set(user.id, {
			id: user.id,
			name: userDisplayName(user) ?? 'someone',
			avatarUrl: user.avatar_url ?? null,
			isAgent: false,
		})
	}
	return index
}

/**
 * index a thread's agents by id.
 *
 * the roster is authoritative for the agents actually in this thread, which the
 * global agent store is not: it only holds agents the viewer owns, so an agent
 * belonging to someone else resolves to nothing there.
 */
export function buildThreadAgentIndex(thread: Thread | null): Map<string, MessageAuthor> {
	const index = new Map<string, MessageAuthor>()
	for (const participant of thread?.participants ?? []) {
		if (participant.kind !== 'agent') continue
		const agent = participant.agent
		index.set(agent.id, {
			id: agent.id,
			name: agent.name,
			avatarUrl: agent.profile_image_url ?? null,
			isAgent: true,
		})
	}
	return index
}

/**
 * the faces to show for the people composing right now.
 *
 * the roster index holds humans only, so an id it does not know is skipped:
 * your own signal never comes back to you, and an agent working on an answer
 * has the generation UI rather than a typing bubble.
 */
export function composingFaces(
	userIds: readonly string[],
	participants: Map<string, MessageAuthor>,
	currentUserId: string | null
): ConversationFace[] {
	const faces: ConversationFace[] = []
	for (const userId of userIds) {
		if (userId === currentUserId) continue
		const author = participants.get(userId)
		if (!author || author.isAgent) continue
		faces.push({
			id: author.id,
			label: author.name,
			avatarUrl: author.avatarUrl,
			isAgent: false,
		})
	}
	return faces
}

/**
 * who wrote a message, or null when it is the viewer's own / unresolvable.
 *
 * a participant who has since left the thread is no longer in the roster, so
 * an unresolved id yields a stable placeholder rather than a blank bubble.
 */
export function resolveMessageAuthor(
	message: Pick<ApiMessage, 'sender_user_id' | 'sender_agent_id'>,
	participants: Map<string, MessageAuthor>,
	agentNames: Map<string, string>,
	agentAvatars: Map<string, string | null>
): MessageAuthor | null {
	if (message.sender_agent_id) {
		const id = message.sender_agent_id
		return {
			id,
			name: agentNames.get(id) ?? 'assistant',
			avatarUrl: agentAvatars.get(id) ?? null,
			isAgent: true,
		}
	}
	const userId = message.sender_user_id
	if (!userId) return null
	return (
		participants.get(userId) ?? { id: userId, name: 'someone', avatarUrl: null, isAgent: false }
	)
}
