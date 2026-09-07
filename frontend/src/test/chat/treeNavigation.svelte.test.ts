/**
 * tests for branch switching past what a page carries.
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread, resetIdCounter } from './fixtures'

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
	agents: { list: [], load: vi.fn(), get: vi.fn(() => null) },
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: { isLoggedIn: true, currentUser: null, currentUserId: 'user_test' },
}))

import { createChatState } from '$lib/chat/createChatState.svelte'
import { branchAlternativeCount, siblingIdsOfKind } from '$lib/chat/helpers'
import { switchBranch } from '$lib/chat/treeNavigation'
import { chat, isPeopleThread } from '$lib/stores/chat.svelte'
import type { ChatState } from '$lib/chat/types'
import type { Thread } from './fixtures'

type Participant = NonNullable<Thread['participants']>[number]

function writer(id: string, is_owner = false): Participant {
	return {
		id: `p_${id}`,
		thread_id: 't1',
		access_level: 'editor',
		is_owner,
		kind: 'user',
		user: { id },
	}
}

const SIBLING_PATH = '/v1/threads/{thread_id}/messages/{message_id}/siblings'

/** a fork with `total` alternatives, of which only `carried` reached the page. */
function seedFork(state: ChatState, carried: number, total: number): void {
	const thread = makeThread({ id: 't1', current_message_id: `c${carried}` })
	state.thread = thread
	state.messageTree.set(
		'p',
		makeApiMessage({ id: 'p', thread_id: 't1', parent_id: null, type: 'user' })
	)
	for (let index = 1; index <= carried; index++) {
		state.messageTree.set(
			`c${index}`,
			makeApiMessage({
				id: `c${index}`,
				thread_id: 't1',
				parent_id: 'p',
				type: 'assistant',
				sender_user_id: null,
				sender_agent_id: 'agent_1',
				created_at: `2026-01-01T00:0${index}:00Z`,
			})
		)
	}
	state.siblingCounts.set('p', total)
	state.currentLeafId = `c${carried}`
}

function overflowMessages(from: number, to: number) {
	const messages = []
	for (let index = from; index <= to; index++) {
		messages.push(
			makeApiMessage({
				id: `c${index}`,
				thread_id: 't1',
				parent_id: 'p',
				type: 'assistant',
				sender_user_id: null,
				sender_agent_id: 'agent_1',
				created_at: `2026-01-01T00:0${index}:00Z`,
			})
		)
	}
	return messages
}

describe('switchBranch sibling overflow', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.POST.mockImplementation((path: string) => {
			if (path === '/v1/threads/{thread_id}/switch') {
				return Promise.resolve({
					data: { ok: true, current_message_id: null },
					error: null,
				})
			}
			return Promise.resolve({
				data: { items: [], next_cursor: null, has_more: false },
				error: null,
			})
		})
	})

	afterEach(() => {
		chat.clear()
	})

	it('pages in the alternatives the branch page could not carry', async () => {
		const state = createChatState()
		seedFork(state, 5, 8)

		let siblingQuery: Record<string, unknown> | undefined
		apiMocks.GET.mockImplementation((path: string, options?: ApiPathOptions) => {
			if (path !== SIBLING_PATH) return Promise.resolve({ data: null, error: null })
			siblingQuery = options?.params?.query
			expect(options?.params?.path?.message_id).toBe('p')
			return Promise.resolve({ data: overflowMessages(6, 8), error: null })
		})

		await switchBranch('c5', 'next', state)

		// the carried branches are the first five, so the rest page from there
		expect(siblingQuery).toMatchObject({ skip: 5 })
		expect(state.messageTree.has('c8')).toBe(true)
		expect(state.currentLeafId).toBe('c6')
	})

	it('leaves a fully loaded fork alone', async () => {
		const state = createChatState()
		seedFork(state, 3, 3)

		apiMocks.GET.mockResolvedValue({ data: [], error: null })

		await switchBranch('c3', 'next', state)

		expect(apiMocks.GET).not.toHaveBeenCalled()
		expect(state.currentLeafId).toBe('c3')
	})

	it('does not fetch when stepping back through loaded alternatives', async () => {
		const state = createChatState()
		seedFork(state, 5, 8)

		apiMocks.GET.mockResolvedValue({ data: [], error: null })

		await switchBranch('c5', 'prev', state)

		expect(apiMocks.GET).not.toHaveBeenCalled()
		expect(state.currentLeafId).toBe('c4')
	})

	it('steps between answers only, never onto user traffic beside them', async () => {
		const state = createChatState()
		seedFork(state, 2, 2)
		// a plain message posted against the same parent is conversation, not an
		// alternative answer - stepping onto it would contradict the indicator.
		state.messageTree.set(
			'u_beside',
			makeApiMessage({
				id: 'u_beside',
				thread_id: 't1',
				parent_id: 'p',
				type: 'user',
				created_at: '2026-01-01T00:03:00Z',
			})
		)
		apiMocks.GET.mockResolvedValue({ data: [], error: null })

		await switchBranch('c2', 'next', state)

		expect(state.currentLeafId).toBe('c2')
	})

	it('reverts the roam when the server rejects the switch', async () => {
		const state = createChatState()
		seedFork(state, 3, 3)
		apiMocks.GET.mockResolvedValue({ data: [], error: null })
		apiMocks.POST.mockImplementation((path: string) => {
			if (path === '/v1/threads/{thread_id}/switch') {
				return Promise.resolve({ data: null, error: { detail: 'forbidden' } })
			}
			return Promise.resolve({ data: null, error: null })
		})
		const logged = vi.spyOn(console, 'error').mockImplementation(() => {})

		await switchBranch('c3', 'prev', state)

		// the server never moved, so neither does the view
		expect(state.currentLeafId).toBe('c3')
		expect(state.thread?.current_message_id).toBe('c3')
		logged.mockRestore()
	})

	it('counts the alternatives at a fork in a people thread', () => {
		const state = createChatState()
		seedFork(state, 2, 2)
		state.thread = makeThread({
			id: 't1',
			current_message_id: 'c2',
			participants: [writer('user_1', true), writer('user_2')],
		})

		expect(isPeopleThread(state.thread)).toBe(true)
		const siblings = siblingIdsOfKind('p', 'response', state.messageChildren, state.messageTree)
		expect(branchAlternativeCount('p', siblings, state.siblingCounts)).toBe(2)
	})
})
