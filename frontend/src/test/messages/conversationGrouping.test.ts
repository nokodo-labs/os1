/**
 * the messages inbox grouping definitions: how one flat conversation list is
 * split into cards, and how a stored choice is resolved back into a grouping.
 */

import type { components } from '$lib/api/types'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Conversation = components['schemas']['Thread']
type Participant = NonNullable<Conversation['participants']>[number]

vi.mock('$app/environment', () => ({ browser: true, dev: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: [], error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => null),
	onAccessTokenChanged: vi.fn(),
}))

const {
	CONVERSATION_GROUPINGS,
	groupConversations,
	readStoredGrouping,
	resolveGroupingId,
	storeGrouping,
} = await import('$lib/messages/grouping')

const STORAGE_KEY = 'messages-group-by'

function participant(id: string): Participant {
	return {
		id: `part_${id}`,
		thread_id: 't',
		access_level: 'editor',
		is_owner: false,
		kind: 'user',
		user: { id, username: id, display_name: id },
	}
}

function conversation(id: string, writerIds: string[]): Conversation {
	return {
		id,
		owner_id: 'user_me',
		title: id,
		tags: [],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
		participants: writerIds.map(participant),
	}
}

const dmA = conversation('dm_a', ['user_me', 'user_alice'])
const groupA = conversation('group_a', ['user_me', 'user_alice', 'user_bob'])
const dmB = conversation('dm_b', ['user_me', 'user_bob'])

/** the inbox order the store hands over: newest activity first. */
const inbox = [dmA, groupA, dmB]

const unreadCounts = new Map([
	['group_a', 1],
	['dm_b', 4],
])
const unreadCountOf = (threadId: string): number => unreadCounts.get(threadId) ?? 0
const idsOf = (threads: Conversation[]): string[] => threads.map((thread) => thread.id)

describe('conversation groupings', () => {
	it('keeps one unlabelled card at the default grouping', () => {
		const groups = groupConversations('default', inbox, unreadCountOf)

		expect(groups).toHaveLength(1)
		expect(groups[0].label).toBe('')
		expect(idsOf(groups[0].threads)).toEqual(['dm_a', 'group_a', 'dm_b'])
	})

	it('splits by read status, newest first inside each card', () => {
		const groups = groupConversations('read-status', inbox, unreadCountOf)

		expect(groups.map((group) => group.label)).toEqual(['unread', 'read'])
		expect(idsOf(groups[0].threads)).toEqual(['group_a', 'dm_b'])
		expect(idsOf(groups[1].threads)).toEqual(['dm_a'])
	})

	it('splits DMs from group chats', () => {
		const groups = groupConversations('kind', inbox, unreadCountOf)

		expect(groups.map((group) => group.label)).toEqual(['people', 'groups'])
		expect(idsOf(groups[0].threads)).toEqual(['dm_a', 'dm_b'])
		expect(idsOf(groups[1].threads)).toEqual(['group_a'])
	})

	it('drops a bucket nothing falls into', () => {
		const groups = groupConversations('read-status', [dmA], unreadCountOf)

		expect(groups.map((group) => group.label)).toEqual(['read'])
	})

	it('carries an icon on every grouping, so the menu and button need no lookup table', () => {
		for (const grouping of CONVERSATION_GROUPINGS) {
			expect(grouping.icon).toBeTypeOf('function')
		}
	})

	it('names the resting grouping default, not none', () => {
		expect(CONVERSATION_GROUPINGS[0].id).toBe('default')
		expect(CONVERSATION_GROUPINGS[0].label).toBe('default')
	})

	it('gives every conversation a bucket in every grouping', () => {
		for (const grouping of CONVERSATION_GROUPINGS) {
			const groups = groupConversations(grouping.id, inbox, unreadCountOf)
			const placed = groups.flatMap((group) => group.threads)

			expect(placed).toHaveLength(inbox.length)
		}
	})
})

describe('stored grouping choice', () => {
	beforeEach(() => {
		window.localStorage.clear()
	})

	it('falls back to the default for a value the definitions do not name', () => {
		expect(resolveGroupingId('by-vibes')).toBe('default')
		expect(resolveGroupingId(null)).toBe('default')
	})

	it('reads the pre-rename none id as the default grouping', () => {
		expect(resolveGroupingId('none')).toBe('default')
	})

	it('reads a stored grouping back', () => {
		storeGrouping('kind')

		expect(window.localStorage.getItem(STORAGE_KEY)).toBe('kind')
		expect(readStoredGrouping()).toBe('kind')
	})

	it('reads the default when nothing is stored, or when what is stored is unknown', () => {
		expect(readStoredGrouping()).toBe('default')

		window.localStorage.setItem(STORAGE_KEY, 'by-vibes')

		expect(readStoredGrouping()).toBe('default')
	})

	it('stops storing the default rather than writing it', () => {
		storeGrouping('read-status')
		storeGrouping('default')

		expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
	})
})
