/**
 * tests for chat tree loading across cache, branch, and rapid navigation.
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread, resetIdCounter } from './fixtures'

type ThreadFixture = ReturnType<typeof makeThread>
type MessageFixture = ReturnType<typeof makeApiMessage>
type ApiPathOptions = {
	params?: {
		path?: { thread_id?: string; message_id?: string }
		query?: Record<string, unknown>
	}
}

const apiMocks = vi.hoisted(() => ({
	GET: vi.fn(),
	POST: vi.fn(),
	PATCH: vi.fn(),
	DELETE: vi.fn(),
}))

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribe: vi.fn(() => () => {}),
		subscribeTypes: vi.fn(() => () => {}),
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

import { createChatState } from '$lib/chat/createChatState.svelte'
import { loadNewerMessages, loadTree } from '$lib/chat/dataLoader'
import { chat } from '$lib/stores/chat.svelte'

/** `/branch` returns a page, not a bare array. */
function makeBranchPage(messages: MessageFixture[], overrides: Record<string, unknown> = {}) {
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
		...overrides,
	}
}

/** let queued continuations run without letting any gated promise settle. */
async function flushMicrotasks(): Promise<void> {
	for (let i = 0; i < 10; i++) await Promise.resolve()
}

/** a promise plus the trigger that settles it. */
function gate(): { wait: Promise<void>; open: () => void } {
	let open = (): void => {}
	const wait = new Promise<void>((resolve) => {
		open = () => resolve()
	})
	return { wait, open }
}

/** the per-user state row the loader reads to find the last-read message. */
function makeUserState(threadId: string, lastReadMessageId: string | null) {
	return {
		thread_id: threadId,
		invite_status: null,
		last_read_message_id: lastReadMessageId,
		muted: false,
		pinned: false,
		archived: false,
	}
}

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
			return Promise.resolve({
				data: makeBranchPage(responses.branches?.[threadId] ?? []),
				error: null,
			})
		}
		return Promise.resolve({ data: null, error: null })
	})
}

describe('loadTree', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.PATCH.mockReset()
		// events/by-message-ids is keyset-paginated: a page, not a bare array
		apiMocks.POST.mockResolvedValue({
			data: { items: [], next_cursor: null, has_more: false },
			error: null,
		})
		// no state row unless a test provides one: the reader is caught up
		apiMocks.PATCH.mockResolvedValue({ data: null, error: null })
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

	it('opens the thread and the user-state reads together, not in sequence', async () => {
		const thread = makeThread({ id: 't7', current_message_id: 'x1' })
		const x1 = makeApiMessage({ id: 'x1', thread_id: 't7', parent_id: null })
		const threadGate = gate()
		const stateGate = gate()

		apiMocks.GET.mockImplementation(async (path: string) => {
			if (path === '/v1/threads/{thread_id}') {
				await threadGate.wait
				return { data: thread, error: null }
			}
			if (path === '/v1/threads/{thread_id}/branch') {
				return { data: makeBranchPage([x1]), error: null }
			}
			return { data: null, error: null }
		})
		apiMocks.PATCH.mockImplementation(async () => {
			await stateGate.wait
			return { data: makeUserState('t7', null), error: null }
		})

		const state = createChatState()
		const loading = loadTree('t7', state)
		await flushMicrotasks()

		// both requests are on the wire while neither has answered
		expect(apiMocks.GET).toHaveBeenCalledWith('/v1/threads/{thread_id}', expect.any(Object))
		expect(apiMocks.PATCH).toHaveBeenCalledWith(
			'/v1/threads/{thread_id}/participants/users/{user_id}',
			expect.any(Object)
		)

		threadGate.open()
		stateGate.open()

		expect(await loading).toBe(true)
		expect(state.messages.map((m) => m.id)).toEqual(['x1'])
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
				return Promise.resolve({ data: makeBranchPage([u2]), error: null })
			}
			if (path === '/v1/threads/{thread_id}/branch') {
				return Promise.resolve({ data: makeBranchPage([]), error: null })
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

describe('opening at the last-read message', () => {
	const thread = makeThread({ id: 't3', current_message_id: 'm9' })
	const m3 = makeApiMessage({
		id: 'm3',
		thread_id: 't3',
		parent_id: null,
		created_at: '2026-01-01T00:00:00Z',
	})
	const m4 = makeApiMessage({
		id: 'm4',
		thread_id: 't3',
		parent_id: 'm3',
		created_at: '2026-01-01T00:01:00Z',
	})
	const m9 = makeApiMessage({
		id: 'm9',
		thread_id: 't3',
		parent_id: 'm4',
		created_at: '2026-01-01T00:02:00Z',
	})

	let branchQueries: Record<string, unknown>[] = []

	/** anchored page holds m3/m4; the tail page (or the leaf cursor) holds m9. */
	function mockAnchoredThread(anchoredPage: unknown = null): void {
		branchQueries = []
		apiMocks.GET.mockImplementation((path: string, options?: ApiPathOptions) => {
			if (path === '/v1/threads/{thread_id}') {
				return Promise.resolve({ data: thread, error: null })
			}
			if (path !== '/v1/threads/{thread_id}/branch') {
				return Promise.resolve({ data: null, error: null })
			}
			const query = options?.params?.query ?? {}
			branchQueries.push(query)
			if (query.anchor_message_id === 'm3') {
				if (anchoredPage) return Promise.resolve({ data: anchoredPage, error: null })
				return Promise.resolve({
					data: null,
					error: { detail: 'message not found in this thread' },
					response: { status: 404 },
				})
			}
			if (query.cursor === 'leaf-1') {
				return Promise.resolve({ data: makeBranchPage([m9]), error: null })
			}
			return Promise.resolve({ data: makeBranchPage([m9]), error: null })
		})
	}

	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.PATCH.mockReset()
		apiMocks.POST.mockResolvedValue({
			data: { items: [], next_cursor: null, has_more: false },
			error: null,
		})
	})

	afterEach(() => {
		chat.clear()
	})

	it('anchors the first page on the reader last-read message', async () => {
		apiMocks.PATCH.mockResolvedValue({ data: makeUserState('t3', 'm3'), error: null })
		mockAnchoredThread(
			makeBranchPage([m3, m4], {
				total: 3,
				skip: 1,
				has_toward_leaf: true,
				cursor_toward_leaf: 'leaf-1',
			})
		)

		const state = createChatState()
		const loaded = await loadTree('t3', state)

		expect(loaded).toBe(true)
		expect(branchQueries[0]).toMatchObject({ anchor_message_id: 'm3' })
		expect(state.initialAnchorMessageId).toBe('m3')
		expect(state.currentLeafId).toBe('m4')
		// the tail is not loaded, so the pin must not drag the reader to it
		expect(state.hasNewerMessages).toBe(true)
		expect(state.autoScroll).toBe(false)
	})

	it('pins the live tail when the reader is caught up', async () => {
		apiMocks.PATCH.mockResolvedValue({ data: makeUserState('t3', 'm9'), error: null })
		mockAnchoredThread()

		const state = createChatState()
		await loadTree('t3', state)

		expect(branchQueries).toHaveLength(1)
		expect(branchQueries[0].anchor_message_id).toBeUndefined()
		expect(state.initialAnchorMessageId).toBeNull()
		expect(state.hasNewerMessages).toBe(false)
	})

	it('falls back to the tail when the anchor cannot be paged', async () => {
		apiMocks.PATCH.mockResolvedValue({ data: makeUserState('t3', 'm3'), error: null })
		mockAnchoredThread()

		const state = createChatState()
		const loaded = await loadTree('t3', state)

		expect(loaded).toBe(true)
		expect(branchQueries).toHaveLength(2)
		expect(branchQueries[1].anchor_message_id).toBeUndefined()
		expect(state.initialAnchorMessageId).toBeNull()
		expect(state.currentLeafId).toBe('m9')
	})

	it('pages toward the leaf and follows the branch down', async () => {
		apiMocks.PATCH.mockResolvedValue({ data: makeUserState('t3', 'm3'), error: null })
		mockAnchoredThread(
			makeBranchPage([m3, m4], {
				total: 3,
				skip: 1,
				has_toward_leaf: true,
				cursor_toward_leaf: 'leaf-1',
			})
		)

		const state = createChatState()
		await loadTree('t3', state)
		await loadNewerMessages('t3', state)

		expect(branchQueries.at(-1)).toMatchObject({ cursor: 'leaf-1' })
		expect(state.currentLeafId).toBe('m9')
		expect(state.messages.map((m) => m.id)).toEqual(['m3', 'm4', 'm9'])
		// tail reached: the pin is allowed again
		expect(state.hasNewerMessages).toBe(false)
	})

	it('does not page down twice for one cursor', async () => {
		apiMocks.PATCH.mockResolvedValue({ data: makeUserState('t3', 'm3'), error: null })
		mockAnchoredThread(
			makeBranchPage([m3, m4], {
				total: 3,
				skip: 1,
				has_toward_leaf: true,
				cursor_toward_leaf: 'leaf-1',
			})
		)

		const state = createChatState()
		await loadTree('t3', state)
		await Promise.all([loadNewerMessages('t3', state), loadNewerMessages('t3', state)])

		const leafPages = branchQueries.filter((query) => query.cursor === 'leaf-1')
		expect(leafPages).toHaveLength(1)
	})
})

describe('one loader owns the message cache', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.PATCH.mockResolvedValue({ data: null, error: null })
		apiMocks.POST.mockResolvedValue({
			data: { items: [], next_cursor: null, has_more: false },
			error: null,
		})
	})

	afterEach(() => {
		chat.clear()
	})

	it('prefetches a branch page and hands its paging state to loadTree', async () => {
		const thread = makeThread({ id: 't4', current_message_id: 'b2' })
		const b1 = makeApiMessage({ id: 'b1', thread_id: 't4', parent_id: null })
		const b2 = makeApiMessage({ id: 'b2', thread_id: 't4', parent_id: 'b1' })
		const alt = makeApiMessage({ id: 'b2alt', thread_id: 't4', parent_id: 'b1' })

		apiMocks.GET.mockImplementation((path: string) => {
			if (path === '/v1/threads/{thread_id}') {
				return Promise.resolve({ data: thread, error: null })
			}
			if (path === '/v1/threads/{thread_id}/branch') {
				return Promise.resolve({
					data: makeBranchPage([b1, b2], {
						total: 5,
						has_toward_root: true,
						cursor_toward_root: 'root-1',
						siblings: [alt],
						sibling_counts: [{ parent_id: 'b1', total: 3 }],
					}),
					error: null,
				})
			}
			return Promise.resolve({ data: null, error: null })
		})

		await chat.threadCache.prefetchThread('t4')
		const branchCalls = apiMocks.GET.mock.calls.filter(
			(call) => call[0] === '/v1/threads/{thread_id}/branch'
		)
		expect(branchCalls).toHaveLength(1)
		expect(
			apiMocks.GET.mock.calls.some((call) => call[0] === '/v1/threads/{thread_id}/messages')
		).toBe(false)

		const state = createChatState()
		expect(await loadTree('t4', state)).toBe(true)

		// served from the prefetched entry, cursors and counts intact
		expect(
			apiMocks.GET.mock.calls.filter((call) => call[0] === '/v1/threads/{thread_id}/branch')
		).toHaveLength(1)
		expect(state.branchCursorTowardRoot).toBe('root-1')
		expect(state.hasMoreMessages).toBe(true)
		expect(state.hasNewerMessages).toBe(false)
		expect(state.siblingCounts.get('b1')).toBe(3)
		expect(state.messageTree.has('b2alt')).toBe(true)
	})

	it('does not race the loader when a hover prefetch is still in flight', async () => {
		const thread = makeThread({ id: 't5', current_message_id: 'c1' })
		const c1 = makeApiMessage({ id: 'c1', thread_id: 't5', parent_id: null })
		mockThreadApi({ threads: { t5: thread }, messages: {}, branches: { t5: [c1] } })

		// hover starts the prefetch, the click right after starts the loader
		const prefetch = chat.prefetchThread('t5')
		const state = createChatState()
		const loaded = await loadTree('t5', state)
		await prefetch

		expect(loaded).toBe(true)
		expect(
			apiMocks.GET.mock.calls.filter((call) => call[0] === '/v1/threads/{thread_id}')
		).toHaveLength(1)
		expect(
			apiMocks.GET.mock.calls.filter((call) => call[0] === '/v1/threads/{thread_id}/branch')
		).toHaveLength(1)
	})

	it('skips the prefetch for a thread the reader has not caught up with', async () => {
		mockThreadApi({ threads: {}, messages: {} })
		chat.unreadCounts.set('t6', 3)

		await chat.prefetchThread('t6')

		// the loader would open on the last-read page, not the tail this warms
		expect(apiMocks.GET).not.toHaveBeenCalled()
	})
})
