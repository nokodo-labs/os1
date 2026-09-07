/**
 * the flows behind the chat info modal: save, share, archive, mute, mark read,
 * delete, and the participant roster. they live here so the modal carries the
 * same behaviour from every surface it opens on, without any of those surfaces
 * having to wire it up.
 */

import { goto } from '$app/navigation'
import { resolve } from '$app/paths'
import { page } from '$app/state'
import { api } from '$lib/api/client'
import {
	archiveThread,
	deleteThread,
	setThreadMuted,
	THREAD_ORIGINATED_TOGGLE,
	updateThread,
} from '$lib/chat/threadActions'
import { chat, isPeopleThread, type Thread } from '$lib/stores/chat.svelte'
import { messages } from '$lib/stores/messages.svelte'
import { modals } from '$lib/stores/modals.svelte'

export type ThreadParticipant = NonNullable<Thread['participants']>[number]

/** mirror a change into every list that already holds the thread. */
function patchOpenViews(threadId: string, patch: Partial<Thread>): void {
	if (chat.activeThread?.id === threadId) chat.activeThread = { ...chat.activeThread, ...patch }
	messages.patchConversation(threadId, patch)
}

/** a thread that just left every list cannot stay open in the chat view. */
async function leaveThreadView(thread: Thread): Promise<void> {
	if (page.url.pathname !== `/c/${thread.id}`) return
	await goto(resolve(isPeopleThread(thread) ? '/messages' : '/'), {
		keepFocus: true,
		noScroll: true,
	})
}

/** rename + retag. returns false when the write failed (it also toasts). */
export async function saveThreadProperties(
	thread: Thread,
	title: string,
	tags: string[]
): Promise<boolean> {
	const nextTitle = title.trim()
	if (!(await updateThread(thread.id, nextTitle, tags))) return false
	patchOpenViews(thread.id, { title: nextTitle || thread.title, tags })
	return true
}

export function shareThread(thread: Thread): void {
	modals.open('resource-access', {
		resourceType: 'thread',
		resourceId: thread.id,
		title: thread.title ?? thread.id,
	})
}

/** archive for the current user, then leave the chat view if that is where we are. */
export async function archiveThreadFromProperties(thread: Thread): Promise<boolean> {
	if (!(await archiveThread(thread.id))) return false
	messages.removeConversation(thread.id)
	await leaveThreadView(thread)
	return true
}

/**
 * mute or unmute for the current user - the same per-participant write the
 * inbox row uses. returns the state that stuck, or null when the write failed.
 */
export async function muteThreadFromProperties(
	thread: Thread,
	muted: boolean
): Promise<boolean | null> {
	const applied = await setThreadMuted(thread.id, muted)
	if (applied !== null) messages.applyMuted(thread.id, applied)
	return applied
}

/** clear the unread badge for the current user, then re-read the counts. */
export async function markThreadReadFromProperties(thread: Thread): Promise<void> {
	await chat.markThreadRead(thread.id)
	await chat.fetchUnreadCounts()
}

/** a roster change lands in the cache and in every list holding the thread. */
function patchParticipants(threadId: string, participants: ThreadParticipant[]): void {
	const cached = chat.threadCache.get(threadId)
	if (cached) chat.threadCache.set({ ...cached, participants })
	chat.updateRecentThread(threadId, (thread) => ({ ...thread, participants }), false)
	patchOpenViews(threadId, { participants })
}

/** re-read the roster after a write. best effort: the write already stuck. */
async function reloadParticipants(threadId: string): Promise<void> {
	const { data, error } = await api.GET('/v1/threads/{thread_id}/participants', {
		params: { path: { thread_id: threadId } },
	})
	if (error || !data) return
	patchParticipants(threadId, data)
}

/** users, groups and agents all join through the one participants endpoint. */
async function addParticipants(
	thread: Thread,
	body: { user_ids?: string[]; agent_ids?: string[]; group_ids?: string[] }
): Promise<boolean> {
	const { error } = await api.POST('/v1/threads/{thread_id}/participants', {
		params: { path: { thread_id: thread.id } },
		body,
	})
	if (error) return false
	await reloadParticipants(thread.id)
	return true
}

export async function addThreadMembers(thread: Thread, userIds: string[]): Promise<boolean> {
	if (userIds.length === 0) return true
	return await addParticipants(thread, { user_ids: userIds })
}

export async function addThreadAgents(thread: Thread, agentIds: string[]): Promise<boolean> {
	if (agentIds.length === 0) return true
	return await addParticipants(thread, { agent_ids: agentIds })
}

/** each participant kind leaves through its own nested route. */
async function deleteParticipant(
	threadId: string,
	participant: ThreadParticipant
): Promise<boolean> {
	if (participant.kind === 'agent') {
		const { error } = await api.DELETE(
			'/v1/threads/{thread_id}/participants/agents/{agent_id}',
			{ params: { path: { thread_id: threadId, agent_id: participant.agent.id } } }
		)
		return !error
	}
	if (participant.kind === 'group') {
		const { error } = await api.DELETE(
			'/v1/threads/{thread_id}/participants/groups/{group_id}',
			{ params: { path: { thread_id: threadId, group_id: participant.group.id } } }
		)
		return !error
	}
	const { error } = await api.DELETE('/v1/threads/{thread_id}/participants/users/{user_id}', {
		params: { path: { thread_id: threadId, user_id: participant.user.id } },
	})
	return !error
}

export async function removeThreadParticipant(
	thread: Thread,
	participant: ThreadParticipant
): Promise<boolean> {
	if (!(await deleteParticipant(thread.id, participant))) return false
	await reloadParticipants(thread.id)
	return true
}

/**
 * the same removal, aimed at yourself: the roster is out of reach afterwards, so
 * the thread leaves the lists and the chat view the way archiving does.
 */
export async function leaveThread(
	thread: Thread,
	participant: ThreadParticipant
): Promise<boolean> {
	if (!(await deleteParticipant(thread.id, participant))) return false
	messages.removeConversation(thread.id)
	chat.removeRecentThread(thread.id)
	await leaveThreadView(thread)
	return true
}

/**
 * per-thread override for whether an agent answers when mentioned.
 * null inherits the agent's own default, so the control is a tri-state.
 */
export async function setThreadAgentMentionReply(
	thread: Thread,
	agentId: string,
	invokeOnMention: boolean | null
): Promise<boolean> {
	const { error } = await api.PATCH('/v1/threads/{thread_id}/participants/agents/{agent_id}', {
		params: { path: { thread_id: thread.id, agent_id: agentId } },
		body: { invoke_on_mention: invokeOnMention },
	})
	if (error) return false
	await reloadParticipants(thread.id)
	return true
}

export function confirmDeleteThread(thread: Thread): void {
	modals.open('confirm-delete', {
		title: 'delete chat',
		description: 'this chat and its messages are removed for everyone in it.',
		toggle: THREAD_ORIGINATED_TOGGLE,
		onDelete: async (alsoOriginated) => {
			const status = await deleteThread(thread.id, {
				deleteOriginatedResources: alsoOriginated,
			})
			if (status !== 204) return false
			messages.removeConversation(thread.id)
			await chat.refreshThreads({ limit: 25 })
			await leaveThreadView(thread)
			return true
		},
	})
}
