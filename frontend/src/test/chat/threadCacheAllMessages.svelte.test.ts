/**
 * tests for ThreadCache.getAllMessages: the whole-tree read behind a thread
 * export. it pages the flat `/messages` list (capped at 200 server-side),
 * returns oldest-first, honours the caller's limit, refuses to spin on a
 * non-advancing page, and never writes the message cache.
 *
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, resetIdCounter } from './fixtures'

type MessageFixture = ReturnType<typeof makeApiMessage>

/** mirrors MESSAGE_LIST_PAGE_LIMIT / MESSAGE_LIST_MAX_PAGES in chat.svelte.ts. */
const PAGE_LIMIT = 200
const MAX_PAGES = 50

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

import { chat } from '$lib/stores/chat.svelte'

type MessagesQuery = { skip?: number; limit?: number; sort_dir?: string }

function queryOf(call: unknown[]): MessagesQuery {
	const options = call[1]
	if (typeof options !== 'object' || options === null) return {}
	const params = Reflect.get(options, 'params')
	if (typeof params !== 'object' || params === null) return {}
	const query = Reflect.get(params, 'query')
	return typeof query === 'object' && query !== null ? query : {}
}

function messagesCalls(): MessagesQuery[] {
	return apiMocks.GET.mock.calls
		.filter((call) => call[0] === '/v1/threads/{thread_id}/messages')
		.map(queryOf)
}

/** a whole tree, flat and branch-blind, as the list endpoint returns it. */
function makeTree(threadId: string, count: number): MessageFixture[] {
	return Array.from({ length: count }, (_, index) =>
		makeApiMessage({ id: `m${index + 1}`, thread_id: threadId, parent_id: null })
	)
}

/** serve `all` as skip/limit pages, so the loop has to page to see everything. */
function mockMessageList(all: MessageFixture[]): void {
	apiMocks.GET.mockImplementation((path: string, options: unknown) => {
		if (path !== '/v1/threads/{thread_id}/messages') {
			return Promise.resolve({ data: null, error: null })
		}
		const { skip = 0, limit = PAGE_LIMIT } = queryOf([path, options])
		return Promise.resolve({ data: all.slice(skip, skip + limit), error: null })
	})
}

describe('ThreadCache.getAllMessages', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
	})

	it('pages the flat list and returns every message oldest-first', async () => {
		const all = makeTree('t1', PAGE_LIMIT + 30)
		mockMessageList(all)

		const messages = await chat.threadCache.getAllMessages('t1', 500)

		expect(messages.map((message) => message.id)).toEqual(all.map((message) => message.id))
		expect(messagesCalls()).toEqual([
			{ skip: 0, limit: PAGE_LIMIT, sort_dir: 'asc' },
			{ skip: PAGE_LIMIT, limit: PAGE_LIMIT, sort_dir: 'asc' },
		])
	})

	it('never asks for more than the endpoint allows per page', async () => {
		mockMessageList(makeTree('t2', 10))

		await chat.threadCache.getAllMessages('t2', 5000)

		for (const query of messagesCalls()) expect(query.limit).toBeLessThanOrEqual(PAGE_LIMIT)
	})

	it('stops at the caller limit without over-fetching', async () => {
		mockMessageList(makeTree('t3', 1000))

		const messages = await chat.threadCache.getAllMessages('t3', 250)

		expect(messages).toHaveLength(250)
		expect(messagesCalls()).toEqual([
			{ skip: 0, limit: PAGE_LIMIT, sort_dir: 'asc' },
			{ skip: PAGE_LIMIT, limit: 50, sort_dir: 'asc' },
		])
	})

	it('gives up after the page cap when pages never run short', async () => {
		// a server that ignores skip: every page is full, so only the cap ends it
		const page = makeTree('t4', PAGE_LIMIT)
		apiMocks.GET.mockResolvedValue({ data: page, error: null })

		const messages = await chat.threadCache.getAllMessages('t4', PAGE_LIMIT * MAX_PAGES * 2)

		expect(messagesCalls()).toHaveLength(MAX_PAGES)
		expect(messages).toHaveLength(PAGE_LIMIT * MAX_PAGES)
	})

	it('stops on an error page and leaves the message cache untouched', async () => {
		apiMocks.GET.mockResolvedValue({ data: null, error: { detail: 'nope' } })

		expect(await chat.threadCache.getAllMessages('t5', 500)).toEqual([])
		expect(messagesCalls()).toHaveLength(1)
		expect(chat.threadCache.getCachedMessages('t5')).toBeNull()
	})

	it('does not write the message cache on a successful read', async () => {
		mockMessageList(makeTree('t6', 12))

		expect(await chat.threadCache.getAllMessages('t6', 500)).toHaveLength(12)
		expect(chat.threadCache.getCachedMessages('t6')).toBeNull()
	})
})
