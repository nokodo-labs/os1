/**
 * tests for the thread cache contract: a warm revisit renders without touching
 * the network, an expired (or explicitly stalled) entry refetches, and message.*
 * events patch the cached window in place instead of invalidating it.
 *
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeStreamMessage, makeThread, resetIdCounter } from './fixtures'

type ThreadFixture = ReturnType<typeof makeThread>
type MessageFixture = ReturnType<typeof makeApiMessage>

/** mirrors CACHE_TTL_MS in chat.svelte.ts, which does not export it. */
const CACHE_TTL_MS = 5 * 60 * 1000

// capture the handler registered via the eventStreamClient subscription helpers
let capturedHandler: ((msg: unknown) => void) | null = null

const apiMocks = vi.hoisted(() => ({
	GET: vi.fn(),
	POST: vi.fn(),
	PATCH: vi.fn(),
	DELETE: vi.fn(),
}))

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribe: vi.fn(() => () => {}),
		subscribeTypes: vi.fn((_types: readonly string[], handler: (msg: unknown) => void) => {
			capturedHandler = handler
			return () => {
				capturedHandler = null
			}
		}),
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
		hasActiveRuns: vi.fn(() => false),
		refresh: vi.fn(async () => {}),
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
		isLoggedIn: true,
		currentUser: null,
		currentUserId: 'user_test',
	},
}))

import type { components } from '$lib/api/types'
import { createChatState } from '$lib/chat/createChatState.svelte'
import { loadTree } from '$lib/chat/dataLoader'
import { chat } from '$lib/stores/chat.svelte'

type ApiEvent = components['schemas']['Event']

/** `/branch` returns a page, not a bare array. */
function makeBranchPage(messages: MessageFixture[]) {
	return {
		messages,
		total: messages.length,
		skip: 0,
		has_toward_root: false,
		has_toward_leaf: false,
		siblings: [],
		sibling_counts: [],
		cursor_toward_root: null,
		cursor_toward_leaf: null,
	}
}

/** a message-scoped event row, as the events cache stores them. */
function makeEvent(id: string, threadId: string, messageId: string): ApiEvent {
	return {
		id,
		type: 'tool.call',
		scope: 'message',
		scope_id: messageId,
		thread_id: threadId,
		message_id: messageId,
		data: {},
		version: 1,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	}
}

function mockThreadApi(thread: ThreadFixture, messages: MessageFixture[]): void {
	apiMocks.GET.mockImplementation((path: string) => {
		if (path === '/v1/threads/{thread_id}') {
			return Promise.resolve({ data: thread, error: null })
		}
		if (path === '/v1/threads/{thread_id}/branch') {
			return Promise.resolve({ data: makeBranchPage(messages), error: null })
		}
		return Promise.resolve({ data: null, error: null })
	})
}

function resetApiMocks(): void {
	apiMocks.GET.mockReset()
	apiMocks.PATCH.mockReset()
	apiMocks.POST.mockReset()
	// no state row: the reader is caught up, so the loader opens the tail
	apiMocks.PATCH.mockResolvedValue({ data: null, error: null })
	// events/by-message-ids is keyset-paginated: a page, not a bare array
	apiMocks.POST.mockResolvedValue({
		data: { items: [], next_cursor: null, has_more: false },
		error: null,
	})
}

/** a two-message thread, seeded exactly as a completed load leaves the cache. */
function seedCachedThread(threadId: string): {
	thread: ThreadFixture
	first: MessageFixture
	second: MessageFixture
} {
	const thread = makeThread({ id: threadId, current_message_id: 'm2' })
	const first = makeApiMessage({ id: 'm1', thread_id: threadId, parent_id: null })
	const second = makeApiMessage({ id: 'm2', thread_id: threadId, parent_id: 'm1' })
	chat.threadCache.set(thread)
	chat.threadCache.setMessages(threadId, [first, second], true)
	return { thread, first, second }
}

describe('warm thread revisits', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		resetApiMocks()
	})

	afterEach(() => {
		chat.clear()
	})

	it('renders a second visit from the cache without any network read', async () => {
		const thread = makeThread({ id: 't1', current_message_id: 'a1' })
		const user = makeApiMessage({ id: 'u1', thread_id: 't1', parent_id: null })
		const assistant = makeApiMessage({
			id: 'a1',
			thread_id: 't1',
			type: 'assistant',
			parent_id: 'u1',
			content: [{ type: 'text', text: 'done' }],
			sender_user_id: null,
			sender_agent_id: 'agent_1',
		})
		mockThreadApi(thread, [user, assistant])

		expect(await loadTree('t1', createChatState())).toBe(true)
		expect(apiMocks.GET).toHaveBeenCalledWith(
			'/v1/threads/{thread_id}/branch',
			expect.any(Object)
		)

		apiMocks.GET.mockClear()
		apiMocks.POST.mockClear()

		const revisit = createChatState()
		expect(await loadTree('t1', revisit)).toBe(true)

		expect(apiMocks.GET).not.toHaveBeenCalled()
		expect(apiMocks.POST).not.toHaveBeenCalled()
		expect(revisit.thread?.id).toBe('t1')
		expect(revisit.currentLeafId).toBe('a1')
		expect(revisit.messages.map((m) => m.id)).toEqual(['u1', 'a1'])
	})
})

describe('cache freshness', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		resetApiMocks()
		vi.useFakeTimers()
	})

	afterEach(() => {
		vi.useRealTimers()
		chat.clear()
	})

	it('refetches once the cache ttl has elapsed', async () => {
		const thread = makeThread({ id: 't2', current_message_id: 'b2' })
		const b1 = makeApiMessage({ id: 'b1', thread_id: 't2', parent_id: null })
		const b2 = makeApiMessage({ id: 'b2', thread_id: 't2', parent_id: 'b1' })
		mockThreadApi(thread, [b1, b2])

		expect(await loadTree('t2', createChatState())).toBe(true)
		apiMocks.GET.mockClear()
		expect(chat.threadCache.getCachedMessages('t2')).not.toBeNull()

		vi.setSystemTime(Date.now() + CACHE_TTL_MS + 1)

		const revisit = createChatState()
		expect(await loadTree('t2', revisit)).toBe(true)

		expect(apiMocks.GET.mock.calls.map((call) => call[0])).toEqual([
			'/v1/threads/{thread_id}',
			'/v1/threads/{thread_id}/branch',
		])
		expect(revisit.messages.map((m) => m.id)).toEqual(['b1', 'b2'])
	})

	it('refetches after markAllStale, before the ttl would expire', async () => {
		const thread = makeThread({ id: 't3', current_message_id: 'c2' })
		const c1 = makeApiMessage({ id: 'c1', thread_id: 't3', parent_id: null })
		const c2 = makeApiMessage({ id: 'c2', thread_id: 't3', parent_id: 'c1' })
		mockThreadApi(thread, [c1, c2])

		expect(await loadTree('t3', createChatState())).toBe(true)
		apiMocks.GET.mockClear()
		expect(chat.threadCache.getCachedMessages('t3')).not.toBeNull()

		chat.threadCache.markAllStale()
		expect(chat.threadCache.get('t3')).toBeNull()
		expect(chat.threadCache.getCachedMessages('t3')).toBeNull()

		const revisit = createChatState()
		expect(await loadTree('t3', revisit)).toBe(true)

		expect(apiMocks.GET.mock.calls.map((call) => call[0])).toEqual([
			'/v1/threads/{thread_id}',
			'/v1/threads/{thread_id}/branch',
		])
		expect(revisit.messages.map((m) => m.id)).toEqual(['c1', 'c2'])
	})
})

describe('message events patch the cache in place', () => {
	/** dispatch one event through the store's handler */
	function dispatch(msg: unknown): void {
		if (!capturedHandler) throw new Error('no handler registered - did you call chat.init()?')
		capturedHandler(msg)
	}

	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		resetApiMocks()
		chat.init()
	})

	afterEach(() => {
		chat.cleanup()
		chat.clear()
		capturedHandler = null
	})

	it('appends a created message to the cached window', () => {
		seedCachedThread('t4')
		const third = makeApiMessage({ id: 'm3', thread_id: 't4', parent_id: 'm2' })

		dispatch(makeStreamMessage('message.created', { ...third }))

		expect(chat.threadCache.getCachedMessages('t4')?.map((m) => m.id)).toEqual([
			'm1',
			'm2',
			'm3',
		])
		expect(apiMocks.GET).not.toHaveBeenCalled()
		expect(apiMocks.POST).not.toHaveBeenCalled()
	})

	it('merges an updated message into the cached window', () => {
		seedCachedThread('t5')

		dispatch(
			makeStreamMessage('message.updated', {
				id: 'm2',
				thread_id: 't5',
				content: [{ type: 'text', text: 'edited' }],
			})
		)

		const cached = chat.threadCache.getCachedMessages('t5')
		expect(cached?.map((m) => m.id)).toEqual(['m1', 'm2'])
		expect(cached?.[1].content).toEqual([{ type: 'text', text: 'edited' }])
		expect(cached?.[0].content).toEqual([{ type: 'text', text: 'hello' }])
		expect(apiMocks.GET).not.toHaveBeenCalled()
	})

	it('drops deleted messages and their events from the cache', () => {
		seedCachedThread('t6')
		chat.threadCache.setEvents(
			't6',
			[makeEvent('e1', 't6', 'm1'), makeEvent('e2', 't6', 'm2')],
			['m1', 'm2']
		)

		dispatch(makeStreamMessage('message.deleted', { thread_id: 't6', deleted_ids: ['m2'] }))

		expect(chat.threadCache.getCachedMessages('t6')?.map((m) => m.id)).toEqual(['m1'])
		const cachedEvents = chat.threadCache.getCachedEvents('t6')
		expect(cachedEvents?.events.map((e) => e.id)).toEqual(['e1'])
		expect(cachedEvents?.messageIds.has('m2')).toBe(false)
		expect(apiMocks.GET).not.toHaveBeenCalled()
	})

	it('drops a single deleted message announced by message_id', () => {
		seedCachedThread('t7')
		chat.threadCache.setEvents('t7', [makeEvent('e1', 't7', 'm1')], ['m1'])

		dispatch(makeStreamMessage('message.deleted', { thread_id: 't7', message_id: 'm1' }))

		expect(chat.threadCache.getCachedMessages('t7')?.map((m) => m.id)).toEqual(['m2'])
		expect(chat.threadCache.getCachedEvents('t7')?.events).toEqual([])
		expect(apiMocks.GET).not.toHaveBeenCalled()
	})
})
