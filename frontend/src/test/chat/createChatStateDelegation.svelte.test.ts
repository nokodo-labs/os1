/**
 * tests for createChatState thread delegation.
 * validates that ctx.thread reads/writes chatStore.activeThread (single source of truth),
 * and that setThread/clearThread properly manage it.
 *
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeThread, resetIdCounter } from './fixtures'

// --- module mocks ---

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribe: vi.fn(() => () => {}),
		subscribeTypes: vi.fn(() => () => {}),
	},
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: null, error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null, response: { status: 204 } }),
	},
	getApiBaseUrl: vi.fn(() => 'http://localhost:1383'),
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => null),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/auth/jwt', () => ({
	getJwtUserId: vi.fn(() => 'user_test'),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: {
		init: vi.fn(),
		cleanup: vi.fn(),
	},
}))

vi.mock('$lib/stores/agents.svelte', () => ({
	agents: {
		list: [],
		load: vi.fn(),
	},
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		isLoggedIn: false,
		currentUser: null,
	},
}))

import { createChatState } from '$lib/chat/createChatState.svelte'
import { chat } from '$lib/stores/chat.svelte'

describe('createChatState thread delegation', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
	})

	afterEach(() => {
		chat.clear()
	})

	it('ctx.thread reads from chatStore.activeThread', () => {
		const state = createChatState()
		const thread = makeThread({ id: 't1', title: 'hello' })

		chat.activeThread = thread

		expect(state.thread?.id).toBe('t1')
		expect(state.thread?.title).toBe('hello')
	})

	it('ctx.thread write updates chatStore.activeThread', () => {
		const state = createChatState()
		const thread = makeThread({ id: 't2', title: 'world' })

		state.thread = thread

		expect(chat.activeThread?.id).toBe('t2')
		expect(chat.activeThread?.title).toBe('world')
	})

	it('ctx.thread is null when no active thread', () => {
		const state = createChatState()

		expect(state.thread).toBeNull()
	})

	it('setThread updates chatStore.activeThread', () => {
		const state = createChatState()
		const thread = makeThread({ id: 't3' })

		state.setThread(thread)

		expect(chat.activeThread?.id).toBe('t3')
		expect(state.thread?.id).toBe('t3')
	})

	it('clearThread nulls chatStore.activeThread', () => {
		const state = createChatState()
		const thread = makeThread({ id: 't4' })
		state.setThread(thread)

		state.clearThread()

		expect(chat.activeThread).toBeNull()
		expect(state.thread).toBeNull()
	})

	it('store update propagates to ctx.thread without re-assignment', () => {
		const state = createChatState()
		const thread = makeThread({ id: 't5', title: 'original' })
		chat.activeThread = thread

		// simulate what chat.svelte.ts#handleStreamEvent does on thread.updated
		chat.activeThread = { ...chat.activeThread!, title: 'updated by event' }

		expect(state.thread?.title).toBe('updated by event')
	})

	it('multiple createChatState instances share the same activeThread', () => {
		const state1 = createChatState()
		const state2 = createChatState()
		const thread = makeThread({ id: 't6' })

		state1.setThread(thread)

		expect(state2.thread?.id).toBe('t6')
	})
})
