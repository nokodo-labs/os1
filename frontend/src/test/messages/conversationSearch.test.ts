/**
 * messages find mode gets its hits from two places: the listed inbox, which is
 * the only side that knows what a DM is called, and `/v1/threads/search`, which
 * is the only side that can read message content.
 */

import type { components } from '$lib/api/types'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Conversation = components['schemas']['Thread']
type Participant = NonNullable<Conversation['participants']>[number]

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

const get = vi.fn()

vi.mock('$lib/api/client', () => ({
	api: {
		GET: (...args: unknown[]) => get(...args),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

const { chat } = await import('$lib/stores/chat.svelte')
const { conversationMatchesName, searchConversations, searchInvites } =
	await import('$lib/messages/conversationSearch')

function participant(id: string, name: string): Participant {
	return {
		id: `part_${id}`,
		thread_id: 't',
		access_level: 'editor',
		is_owner: false,
		kind: 'user',
		user: { id, username: name, display_name: name },
	}
}

function conversation(id: string, title: string | null, other: string): Conversation {
	return {
		id,
		owner_id: 'user_me',
		title,
		tags: [],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
		participants: [participant('user_me', 'me'), participant(`user_${other}`, other)],
	}
}

const alice = conversation('t_alice', null, 'alice')
const bob = conversation('t_bob', null, 'bob')

beforeEach(() => {
	get.mockReset()
	get.mockResolvedValue({ data: { items: [] }, error: null })
})

describe('conversationMatchesName', () => {
	it('matches an untitled DM on the name its row shows', () => {
		expect(conversationMatchesName(alice, 'ali', 'user_me')).toBe(true)
		expect(conversationMatchesName(bob, 'ali', 'user_me')).toBe(false)
	})

	it('matches a group on its own title', () => {
		const group = conversation('t_group', 'weekend plans', 'alice')
		expect(conversationMatchesName(group, 'weekend', 'user_me')).toBe(true)
	})

	it('never matches on an empty query', () => {
		expect(conversationMatchesName(alice, '   ', 'user_me')).toBe(false)
	})
})

describe('searchConversations', () => {
	it('lists the inbox matches first, scoped to people threads', async () => {
		const found = await searchConversations({
			query: 'alice',
			userId: 'user_me',
			loaded: [alice, bob],
		})

		expect(found).toEqual([alice])
		expect(get).toHaveBeenCalledWith(
			'/v1/threads/search',
			expect.objectContaining({
				params: {
					query: expect.objectContaining({
						q: 'alice',
						participant_scope: 'people',
						not_archived_by: 'user_me',
						not_invite_pending_for: 'user_me',
					}),
				},
			})
		)
	})

	it('adds a server hit the inbox did not list, in the shape the rows need', async () => {
		const carol = conversation('t_carol', null, 'carol')
		chat.threadCache.set(carol)
		// the search payload carries no roster - the cached thread is what renders
		get.mockResolvedValue({
			data: { items: [{ ...carol, participants: [] }] },
			error: null,
		})

		const found = await searchConversations({
			query: 'dinner',
			userId: 'user_me',
			loaded: [alice],
		})

		expect(found).toEqual([carol])
		expect(found[0].participants).toHaveLength(2)
	})

	it('drops a hit it cannot name rather than drawing an anonymous row', async () => {
		get.mockResolvedValue({
			data: { items: [{ ...conversation('t_unknown', null, 'dave'), participants: [] }] },
			error: null,
		})

		const found = await searchConversations({
			query: 'dinner',
			userId: 'user_me',
			loaded: [],
		})

		expect(found).toEqual([])
	})

	it('never lists a conversation twice', async () => {
		chat.threadCache.set(alice)
		get.mockResolvedValue({ data: { items: [alice] }, error: null })

		const found = await searchConversations({
			query: 'alice',
			userId: 'user_me',
			loaded: [alice],
		})

		expect(found).toHaveLength(1)
	})

	it('asks nothing of the server for an empty query', async () => {
		const found = await searchConversations({ query: '  ', userId: 'user_me', loaded: [alice] })

		expect(found).toEqual([])
		expect(get).not.toHaveBeenCalled()
	})
})

describe('searchInvites', () => {
	it('filters the pending requests already held, with no second call', () => {
		const invite = conversation('t_invite', null, 'alice')

		expect(searchInvites([invite], 'ali', 'user_me')).toEqual([invite])
		expect(searchInvites([invite], 'zoe', 'user_me')).toEqual([])
		expect(get).not.toHaveBeenCalled()
	})
})
