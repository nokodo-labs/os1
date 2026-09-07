/**
 * how the messages inbox splits into cards.
 *
 * a grouping is a definition, not a branch: an ordered list of buckets, each
 * with a lowercase card header and a predicate. the first bucket that matches
 * takes the conversation, buckets that stay empty are dropped, and the order
 * the inbox arrived in is preserved inside every bucket. adding a grouping
 * means adding one entry to `CONVERSATION_GROUPINGS` - label, icon and buckets
 * travel together, so the menu and the group-by button need no changes.
 */

import { browser } from '$app/environment'
import ChatCheck from '$lib/components/icons/ChatCheck.svelte'
import ListBullet from '$lib/components/icons/ListBullet.svelte'
import UserGroup from '$lib/components/icons/UserGroup.svelte'
import { threadKind, type Thread } from '$lib/stores/chat.svelte'
import type { Component } from 'svelte'

export type ConversationGroupingId = 'default' | 'read-status' | 'kind'

/** the glyph a grouping wears in the menu and on the group-by button. */
export type ConversationGroupingIcon = Component<{
	class?: string
	strokeWidth?: string | number
	variant?: 'outline' | 'solid'
}>

/** what a bucket predicate gets to look at. per-user state is passed in, not read here. */
export interface ConversationGroupInput {
	thread: Thread
	unreadCount: number
}

export interface ConversationBucket {
	id: string
	/** the card header. empty means the card carries no header. */
	label: string
	match: (input: ConversationGroupInput) => boolean
}

export interface ConversationGrouping {
	id: ConversationGroupingId
	/** how the grouping names itself in the group-by menu. */
	label: string
	icon: ConversationGroupingIcon
	buckets: readonly ConversationBucket[]
}

/** one card holding the conversations a bucket took. */
export interface ConversationGroup {
	id: string
	label: string
	threads: Thread[]
}

export const DEFAULT_CONVERSATION_GROUPING: ConversationGroupingId = 'default'

export const CONVERSATION_GROUPINGS: readonly ConversationGrouping[] = [
	{
		id: 'default',
		label: 'default',
		icon: ListBullet,
		buckets: [{ id: 'all', label: '', match: () => true }],
	},
	{
		id: 'read-status',
		label: 'read status',
		icon: ChatCheck,
		buckets: [
			{ id: 'unread', label: 'unread', match: ({ unreadCount }) => unreadCount > 0 },
			{ id: 'read', label: 'read', match: () => true },
		],
	},
	{
		id: 'kind',
		label: 'DM vs groupchat',
		icon: UserGroup,
		buckets: [
			{
				id: 'people',
				label: 'people',
				match: ({ thread }) => threadKind(thread) !== 'group',
			},
			{ id: 'groups', label: 'groups', match: () => true },
		],
	},
]

export function groupingById(id: ConversationGroupingId): ConversationGrouping {
	return (
		CONVERSATION_GROUPINGS.find((grouping) => grouping.id === id) ?? CONVERSATION_GROUPINGS[0]
	)
}

/**
 * anything the definition list does not name reads as the default grouping - which is
 * also what the pre-rename `none` id resolves to, though the default was never stored.
 */
export function resolveGroupingId(raw: string | null | undefined): ConversationGroupingId {
	const match = CONVERSATION_GROUPINGS.find((grouping) => grouping.id === raw)
	return match ? match.id : DEFAULT_CONVERSATION_GROUPING
}

export function groupConversations(
	groupingId: ConversationGroupingId,
	threads: readonly Thread[],
	unreadCountOf: (threadId: string) => number
): ConversationGroup[] {
	const buckets = groupingById(groupingId).buckets
	const filled = buckets.map(
		(bucket): ConversationGroup => ({ id: bucket.id, label: bucket.label, threads: [] })
	)
	for (const thread of threads) {
		const input: ConversationGroupInput = { thread, unreadCount: unreadCountOf(thread.id) }
		const index = buckets.findIndex((bucket) => bucket.match(input))
		if (index !== -1) filled[index].threads.push(thread)
	}
	return filled.filter((group) => group.threads.length > 0)
}

const STORAGE_KEY = 'messages-group-by'

/** the choice is a local preference for now; a synced one would replace this pair. */
export function readStoredGrouping(): ConversationGroupingId {
	if (!browser) return DEFAULT_CONVERSATION_GROUPING
	try {
		return resolveGroupingId(window.localStorage.getItem(STORAGE_KEY))
	} catch {
		return DEFAULT_CONVERSATION_GROUPING
	}
}

export function storeGrouping(id: ConversationGroupingId): void {
	if (!browser) return
	try {
		if (id === DEFAULT_CONVERSATION_GROUPING) window.localStorage.removeItem(STORAGE_KEY)
		else window.localStorage.setItem(STORAGE_KEY, id)
	} catch {
		// storage unavailable: the choice simply does not survive a reload
	}
}
