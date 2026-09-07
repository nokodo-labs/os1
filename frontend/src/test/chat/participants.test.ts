import {
	buildParticipantIndex,
	composingFaces,
	resolveMessageAuthor,
	type MessageAuthor,
} from '$lib/chat/participants'
import type { Thread } from '$lib/stores/chat.svelte'
import { describe, expect, it } from 'vitest'
import { makeThread } from './fixtures'

function threadWithUsers(
	users: Array<{ id: string; display_name?: string | null; username?: string | null }>
): Thread {
	return makeThread({
		id: 'thread_1',
		participants: users.map((user) => ({
			id: `participant_${user.id}`,
			thread_id: 'thread_1',
			is_owner: false,
			kind: 'user' as const,
			user: {
				id: user.id,
				display_name: user.display_name ?? null,
				username: user.username ?? null,
				avatar_url: null,
			},
		})),
	})
}

describe('buildParticipantIndex', () => {
	it('indexes humans by id, preferring display name', () => {
		const index = buildParticipantIndex(
			threadWithUsers([{ id: 'user_1', display_name: 'Ada', username: 'ada99' }])
		)

		expect(index.get('user_1')).toMatchObject({ id: 'user_1', name: 'Ada' })
	})

	it('falls back to the username when there is no display name', () => {
		const index = buildParticipantIndex(
			threadWithUsers([{ id: 'user_1', display_name: null, username: 'ada99' }])
		)

		expect(index.get('user_1')?.name).toBe('ada99')
	})

	it('is empty for a thread with no roster', () => {
		expect(buildParticipantIndex(null).size).toBe(0)
	})
})

describe('composingFaces', () => {
	const roster = buildParticipantIndex(
		threadWithUsers([
			{ id: 'user_me', display_name: 'me' },
			{ id: 'user_ada', display_name: 'Ada' },
			{ id: 'user_bob', display_name: 'Bob' },
		])
	)

	it('names every other person composing, in signal order', () => {
		const faces = composingFaces(['user_bob', 'user_ada'], roster, 'user_me')

		expect(faces.map((face) => face.label)).toEqual(['Bob', 'Ada'])
	})

	it('never shows you your own composing', () => {
		expect(composingFaces(['user_me', 'user_ada'], roster, 'user_me')).toHaveLength(1)
		expect(composingFaces(['user_me'], roster, 'user_me')).toEqual([])
	})

	it('never shows an agent: generation has its own UI', () => {
		const withAgent = new Map<string, MessageAuthor>(roster)
		withAgent.set('agent_1', {
			id: 'agent_1',
			name: 'researcher',
			avatarUrl: null,
			isAgent: true,
		})

		expect(composingFaces(['agent_1', 'user_ada'], withAgent, 'user_me')).toEqual([
			{ id: 'user_ada', label: 'Ada', avatarUrl: null, isAgent: false },
		])
	})

	it('skips an id the roster does not know', () => {
		expect(composingFaces(['user_ghost'], roster, 'user_me')).toEqual([])
	})
})

describe('resolveMessageAuthor', () => {
	const participants = buildParticipantIndex(
		threadWithUsers([{ id: 'user_1', display_name: 'Ada' }])
	)
	const agentNames = new Map([['agent_1', 'researcher']])
	const agentAvatars = new Map<string, string | null>([['agent_1', null]])

	it('resolves a human from the roster', () => {
		const author = resolveMessageAuthor(
			{ sender_user_id: 'user_1', sender_agent_id: null },
			participants,
			agentNames,
			agentAvatars
		)

		expect(author).toMatchObject({ name: 'Ada', isAgent: false })
	})

	it('resolves an agent by id', () => {
		const author = resolveMessageAuthor(
			{ sender_user_id: null, sender_agent_id: 'agent_1' },
			participants,
			agentNames,
			agentAvatars
		)

		expect(author).toMatchObject({ name: 'researcher', isAgent: true })
	})

	it('still names a participant who has left the thread', () => {
		// they are gone from the roster, but their messages remain in the tree
		const author = resolveMessageAuthor(
			{ sender_user_id: 'user_gone', sender_agent_id: null },
			participants,
			agentNames,
			agentAvatars
		)

		expect(author).toMatchObject({ id: 'user_gone', name: 'someone' })
	})

	it('returns null when a message has no sender at all', () => {
		expect(
			resolveMessageAuthor(
				{ sender_user_id: null, sender_agent_id: null },
				participants,
				agentNames,
				agentAvatars
			)
		).toBeNull()
	})
})
