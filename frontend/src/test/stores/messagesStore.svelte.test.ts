/**
 * tests for the messages store: the list mutations the conversation row menu
 * drives (remove, patch, muted set) and the inbox page cache that has to
 * survive the app being reopened.
 */

import type { components } from '$lib/api/types'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Conversation = components['schemas']['Thread']
type ThreadQuery = {
	limit?: number
	skip?: number
	participant_scope?: string
	not_invite_pending_for?: string
	invite_pending_for?: string
	muted_by?: string
	include_last_message?: boolean
}

/** queries the inbox list issued, and the canned responses it gets back. */
const inboxQueries: ThreadQuery[] = []
const inboxResponses: { data?: Conversation[]; error?: unknown }[] = []
/** every thread listing, inbox or not, in call order. */
const threadQueries: ThreadQuery[] = []

vi.mock('$app/environment', () => ({ browser: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn((path: string, init?: { params?: { query?: ThreadQuery } }) => {
			const query = init?.params?.query
			if (path === '/v1/threads' && query) threadQueries.push(query)
			if (path === '/v1/threads' && query?.not_invite_pending_for) {
				inboxQueries.push(query)
				return Promise.resolve(inboxResponses.shift() ?? { data: [], error: null })
			}
			return Promise.resolve({ data: [], error: null })
		}),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: { currentUserId: 'user_me' },
}))

vi.mock('$lib/stores/storeEvents', () => ({
	STORE_EVENT_TYPES: { chat: [], resourceAccessResource: [], notifications: [], typing: [] },
	storeEventData: vi.fn(() => ({})),
	storeEventString: vi.fn(() => null),
	subscribeToStoreEvents: vi.fn(() => () => {}),
}))

const { messages } = await import('$lib/stores/messages.svelte')
const { chat } = await import('$lib/stores/chat.svelte')

function makeThread(id: string, title: string): Conversation {
	return {
		id,
		owner_id: 'user_me',
		title,
		tags: [],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
	}
}

describe('messages store list mutations', () => {
	beforeEach(() => {
		messages.clear()
		chat.unreadCounts.clear()
		messages.conversations = [makeThread('t1', 'one'), makeThread('t2', 'two')]
	})

	it('removes a conversation and forgets its muted flag', () => {
		messages.applyMuted('t1', true)
		expect(messages.isMuted('t1')).toBe(true)

		messages.removeConversation('t1')

		expect(messages.conversations.map((t) => t.id)).toEqual(['t2'])
		expect(messages.isMuted('t1')).toBe(false)
	})

	it('patches a conversation without moving it', () => {
		messages.patchConversation('t2', { title: 'renamed', tags: ['a'] })

		expect(messages.conversations.map((t) => t.id)).toEqual(['t1', 't2'])
		expect(messages.conversations[1].title).toBe('renamed')
		expect(messages.conversations[1].tags).toEqual(['a'])
	})

	it('ignores a patch for a conversation it does not list', () => {
		messages.patchConversation('missing', { title: 'nope' })

		expect(messages.conversations.map((t) => t.title)).toEqual(['one', 'two'])
	})

	it('toggles the muted flag both ways', () => {
		messages.applyMuted('t1', true)
		messages.applyMuted('t1', false)

		expect(messages.isMuted('t1')).toBe(false)
	})
})

describe('messages store inbox page cache', () => {
	beforeEach(() => {
		messages.clear()
		chat.unreadCounts.clear()
		inboxQueries.length = 0
		inboxResponses.length = 0
	})

	async function loadTwoPages(): Promise<void> {
		inboxResponses.push({ data: [makeThread('t1', 'one'), makeThread('t2', 'two')] })
		inboxResponses.push({ data: [makeThread('t3', 'three'), makeThread('t4', 'four')] })
		await messages.load({ limit: 2 })
		await messages.loadMore()
	}

	it('scopes the first page to people conversations', async () => {
		inboxResponses.push({ data: [makeThread('t1', 'one')] })

		await messages.load({ limit: 2 })

		expect(inboxQueries).toHaveLength(1)
		expect(inboxQueries[0].participant_scope).toBe('people')
		expect(inboxQueries[0].limit).toBe(2)
		expect(inboxQueries[0].skip).toBe(0)
	})

	it('serves a reopen from cache instead of falling back to page one', async () => {
		await loadTwoPages()
		expect(messages.conversations.map((t) => t.id)).toEqual(['t1', 't2', 't3', 't4'])

		await messages.load()

		expect(inboxQueries).toHaveLength(2)
		expect(messages.conversations.map((t) => t.id)).toEqual(['t1', 't2', 't3', 't4'])
		expect(messages.isLoading).toBe(false)
	})

	it('refetches every loaded page in one call once the cache goes stale', async () => {
		await loadTwoPages()

		messages.invalidate()
		inboxResponses.push({
			data: [
				makeThread('t1', 'one'),
				makeThread('t2', 'two'),
				makeThread('t3', 'three'),
				makeThread('t4', 'four'),
			],
		})
		await messages.load()

		expect(inboxQueries).toHaveLength(3)
		expect(inboxQueries[2].limit).toBe(4)
		expect(inboxQueries[2].skip).toBe(0)
		expect(messages.conversations.map((t) => t.id)).toEqual(['t1', 't2', 't3', 't4'])
		expect(messages.hasMore).toBe(true)
	})

	it('keeps rendered data and hasLoaded when the cache is invalidated', async () => {
		inboxResponses.push({ data: [makeThread('t1', 'one')] })
		await messages.load({ limit: 2 })

		messages.invalidate()

		expect(messages.hasLoaded).toBe(true)
		expect(messages.conversations.map((t) => t.id)).toEqual(['t1'])
	})

	it('keeps the listed conversations when a refetch fails', async () => {
		inboxResponses.push({ data: [makeThread('t1', 'one')] })
		await messages.load({ limit: 2 })

		messages.invalidate()
		inboxResponses.push({ error: { detail: 'boom' } })
		await messages.load()

		expect(messages.conversations.map((t) => t.id)).toEqual(['t1'])
	})

	it('drops the cache on clear so the next load starts from page one', async () => {
		await loadTwoPages()

		messages.clear()
		inboxResponses.push({ data: [makeThread('t1', 'one'), makeThread('t2', 'two')] })
		await messages.load({ limit: 2 })

		expect(inboxQueries[2].limit).toBe(2)
		expect(messages.conversations.map((t) => t.id)).toEqual(['t1', 't2'])
	})
})

describe('messages store last message', () => {
	beforeEach(() => {
		messages.clear()
		chat.unreadCounts.clear()
		inboxQueries.length = 0
		inboxResponses.length = 0
		threadQueries.length = 0
	})

	it('asks every inbox page for the last message of each row', async () => {
		inboxResponses.push({ data: [makeThread('t1', 'one'), makeThread('t2', 'two')] })
		inboxResponses.push({ data: [makeThread('t3', 'three'), makeThread('t4', 'four')] })
		await messages.load({ limit: 2 })
		await messages.loadMore()

		expect(inboxQueries).toHaveLength(2)
		for (const query of inboxQueries) expect(query.include_last_message).toBe(true)
	})

	it('leaves it off the listings whose rows render no preview', async () => {
		await messages.loadMuted()
		await messages.loadInvites()

		const others = threadQueries.filter((q) => q.muted_by || q.invite_pending_for)
		expect(others).toHaveLength(2)
		for (const query of others) expect(query.include_last_message).toBeUndefined()
	})
})
