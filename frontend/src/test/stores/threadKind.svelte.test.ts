import { isPeopleThread, threadKind, threadWriterCount, type Thread } from '$lib/stores/chat.svelte'
import { describe, expect, it } from 'vitest'
import { makeThread } from '../chat/fixtures'

type Participant = NonNullable<Thread['participants']>[number]
type Level = 'reader' | 'editor' | 'admin' | null

function user(id: string, access_level: Level, is_owner = false): Participant {
	return {
		id: `p_${id}`,
		thread_id: 'thread_1',
		access_level,
		is_owner,
		kind: 'user',
		user: { id },
	}
}

function group(id: string, access_level: Level): Participant {
	return {
		id: `p_${id}`,
		thread_id: 'thread_1',
		access_level,
		is_owner: false,
		kind: 'group',
		group: { id, name: id },
	}
}

function agent(id: string, access_level: Level): Participant {
	return {
		id: `p_${id}`,
		thread_id: 'thread_1',
		access_level,
		is_owner: false,
		kind: 'agent',
		agent: { id, name: id },
	}
}

function thread(participants: Participant[]): Thread {
	return makeThread({ owner_id: 'owner', participants })
}

describe('threadKind', () => {
	it('a lone writer with spectators is a normal chat', () => {
		const t = thread([user('owner', 'admin', true), user('spectator', 'reader')])
		expect(threadWriterCount(t)).toBe(1)
		expect(threadKind(t)).toBe('solo')
	})

	it('two writers make a DM, whoever else is watching', () => {
		const t = thread([
			user('owner', 'admin', true),
			user('friend', 'editor'),
			user('lurker', 'reader'),
		])
		expect(threadWriterCount(t)).toBe(2)
		expect(threadKind(t)).toBe('direct')
	})

	it('three or more writers make a group chat', () => {
		const t = thread([user('owner', 'admin', true), user('a', 'editor'), user('b', 'admin')])
		expect(threadWriterCount(t)).toBe(3)
		expect(threadKind(t)).toBe('group')
	})

	it('a writer group is a group chat even when its members are not counted', () => {
		const t = thread([user('owner', 'admin', true), group('team', 'editor')])
		expect(threadWriterCount(t)).toBe(1)
		expect(threadKind(t)).toBe('group')
	})

	it('a read-only group does not shape the thread', () => {
		expect(
			threadKind(thread([user('owner', 'admin', true), group('audience', 'reader')]))
		).toBe('solo')
	})

	it('agents never count as writers', () => {
		expect(threadKind(thread([user('owner', 'admin', true), agent('bot', 'editor')]))).toBe(
			'solo'
		)
	})

	it('counts a user once even if listed twice', () => {
		const t = thread([
			user('owner', 'admin', true),
			user('owner', 'editor'),
			user('x', 'editor'),
		])
		expect(threadWriterCount(t)).toBe(2)
		expect(threadKind(t)).toBe('direct')
	})
})

describe('isPeopleThread', () => {
	it('is true only when more than one user can write', () => {
		expect(isPeopleThread(thread([user('owner', 'admin', true)]))).toBe(false)
		expect(isPeopleThread(thread([user('owner', 'admin', true), agent('bot', 'editor')]))).toBe(
			false
		)
		expect(isPeopleThread(thread([user('owner', 'admin', true), user('s', 'reader')]))).toBe(
			false
		)
		expect(isPeopleThread(thread([user('owner', 'admin', true), group('g', 'reader')]))).toBe(
			false
		)
		expect(isPeopleThread(thread([user('owner', 'admin', true), user('f', 'editor')]))).toBe(
			true
		)
		expect(isPeopleThread(thread([user('owner', 'admin', true), group('g', 'editor')]))).toBe(
			true
		)
	})
})
