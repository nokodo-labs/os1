/**
 * tests for chat tree loading across cache, branch, and rapid navigation.
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread, resetIdCounter } from './fixtures'

type ThreadFixture = ReturnType<typeof makeThread>
type MessageFixture = ReturnType<typeof makeApiMessage>
type ApiPathOptions = { params?: { path?: { thread_id?: string } } }

const apiMocks = vi.hoisted(() => ({
	GET: vi.fn(),
	POST: vi.fn(),
	PATCH: vi.fn(),
	DELETE: vi.fn(),
}))

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribe: vi.fn(() => () => {}),
	},
}))

vi.mock('$lib/api/client', () => ({
	api: apiMocks,
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
		getRunsForThread: vi.fn(() => []),
	},
}))

vi.mock('$lib/stores/agents.svelte', () => ({
	agents: {
		list: [],
		load: vi.fn(),
		get: vi.fn(() => null),
	},
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		isLoggedIn: false,
		currentUser: null,
	},
}))

import { createChatState } from '$lib/chat/createChatState.svelte'
import { loadTree } from '$lib/chat/dataLoader'
import { chat } from '$lib/stores/chat.svelte'

function mockThreadApi(responses: {
	threads: Record<string, ThreadFixture>
	messages: Record<string, MessageFixture[]>
	branches?: Record<string, MessageFixture[]>
}): void {
	apiMocks.GET.mockImplementation((path: string, options?: ApiPathOptions) => {
		const threadId = options?.params?.path?.thread_id
		if (!threadId) return Promise.resolve({ data: null, error: null })
		if (path === '/v1/threads/{thread_id}') {
			return Promise.resolve({ data: responses.threads[threadId] ?? null, error: null })
		}
		if (path === '/v1/threads/{thread_id}/messages') {
			return Promise.resolve({ data: responses.messages[threadId] ?? [], error: null })
		}
		if (path === '/v1/threads/{thread_id}/branch') {
			return Promise.resolve({ data: responses.branches?.[threadId] ?? [], error: null })
		}
		return Promise.resolve({ data: null, error: null })
	})
}

describe('loadTree', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.POST.mockResolvedValue({ data: [], error: null })
	})

	afterEach(() => {
		chat.clear()
	})

	it('bypasses a message cache that is missing the selected leaf', async () => {
		const thread = makeThread({ id: 't1', current_message_id: 'a1' })
		const user = makeApiMessage({
			id: 'u1',
			thread_id: 't1',
			type: 'user',
			parent_id: null,
		})
		const assistant = makeApiMessage({
			id: 'a1',
			thread_id: 't1',
			type: 'assistant',
			parent_id: 'u1',
			content: [{ type: 'text', text: 'done' }],
			sender_user_id: null,
			sender_agent_id: 'agent_1',
		})

		chat.threadCache.set(thread)
		chat.threadCache.setMessages('t1', [user], true)
		mockThreadApi({
			threads: { t1: thread },
			messages: { t1: [user] },
			branches: { t1: [user, assistant] },
		})

		const state = createChatState()
		const loaded = await loadTree('t1', state)

		expect(loaded).toBe(true)
		expect(state.currentLeafId).toBe('a1')
		expect(state.messages.map((m) => m.id)).toEqual(['u1', 'a1'])
		expect(apiMocks.GET).toHaveBeenCalledWith(
			'/v1/threads/{thread_id}/branch',
			expect.any(Object)
		)
	})

	it('does not let a stale route load overwrite the current thread', async () => {
		let resolveFirstThread: (value: { data: ThreadFixture; error: null }) => void = () => {}
		const firstThreadPromise = new Promise<{ data: ThreadFixture; error: null }>((resolve) => {
			resolveFirstThread = resolve
		})

		const t1 = makeThread({ id: 't1', current_message_id: 'u1' })
		const t2 = makeThread({ id: 't2', current_message_id: 'u2' })
		const u1 = makeApiMessage({ id: 'u1', thread_id: 't1' })
		const u2 = makeApiMessage({ id: 'u2', thread_id: 't2' })

		apiMocks.GET.mockImplementation((path: string, options?: ApiPathOptions) => {
			const threadId = options?.params?.path?.thread_id
			if (path === '/v1/threads/{thread_id}' && threadId === 't1') {
				return firstThreadPromise
			}
			if (path === '/v1/threads/{thread_id}' && threadId === 't2') {
				return Promise.resolve({ data: t2, error: null })
			}
			if (path === '/v1/threads/{thread_id}/messages' && threadId === 't2') {
				return Promise.resolve({ data: [u2], error: null })
			}
			if (path === '/v1/threads/{thread_id}/branch' && threadId === 't2') {
				return Promise.resolve({ data: [u2], error: null })
			}
			return Promise.resolve({ data: [], error: null })
		})

		const state = createChatState()
		const staleLoad = loadTree('t1', state)
		state.clearThread()
		const currentLoad = await loadTree('t2', state)

		resolveFirstThread({ data: t1, error: null })
		const staleResult = await staleLoad

		expect(currentLoad).toBe(true)
		expect(staleResult).toBe(false)
		expect(state.thread?.id).toBe('t2')
		expect(state.currentLeafId).toBe('u2')
		expect(state.messages.map((m) => m.id)).toEqual(['u2'])
		expect(chat.activeThread?.id).toBe('t2')
		expect(u1.id).toBe('u1')
	})
})
