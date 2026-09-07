/**
 * tests for scroll-driven paging in createChatState.
 *
 * a thread that opens mid-history parks the view with a programmatic scroll,
 * and both edges of a short window sit inside their trigger distances at once -
 * so these cover what may NOT page (the opening scroll, a page restore, the
 * second direction while one is in flight) and what still must (a reader
 * scrolling to an edge, a window too short to fill the screen).
 *
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread, resetIdCounter } from './fixtures'

type MessageFixture = ReturnType<typeof makeApiMessage>
type ApiPathOptions = {
	params?: {
		path?: { thread_id?: string }
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
import { loadTree } from '$lib/chat/dataLoader'
import type { ChatState } from '$lib/chat/types'
import { chat } from '$lib/stores/chat.svelte'

const THREAD_ID = 'thread_paging'

function makeBranchPage(messages: MessageFixture[], overrides: Record<string, unknown> = {}) {
	return {
		messages,
		total: 400,
		skip: 100,
		has_toward_root: true,
		has_toward_leaf: true,
		siblings: [],
		sibling_counts: [],
		cursor_toward_root: 'root-1',
		cursor_toward_leaf: 'leaf-1',
		...overrides,
	}
}

interface FakeContainer {
	el: HTMLElement
	/** grow or shrink the transcript, the way a landed page does. */
	setHeight(height: number): void
	height(): number
}

/** a fake scroll container whose measurements the test drives directly. */
function makeContainer(scrollHeight: number, clientHeight: number): FakeContainer {
	const el = document.createElement('div')
	let height = scrollHeight
	Object.defineProperty(el, 'scrollHeight', { configurable: true, get: () => height })
	Object.defineProperty(el, 'clientHeight', { configurable: true, get: () => clientHeight })
	return {
		el,
		setHeight(next: number) {
			height = next
		},
		height: () => height,
	}
}

let branchQueries: Record<string, unknown>[] = []
/** resolvers for in-flight cursor pages, so a test can hold one open. */
let heldPages: Map<string, (value: unknown) => void>
let holdCursors: Set<string>

function mockThread(): void {
	branchQueries = []
	heldPages = new Map()
	holdCursors = new Set()
	// a mid-history window: pages are available in both directions from it
	const thread = makeThread({ id: THREAD_ID, current_message_id: 'm_1' })

	apiMocks.GET.mockImplementation((path: string, options?: ApiPathOptions) => {
		if (path === '/v1/threads/{thread_id}') {
			return Promise.resolve({ data: thread, error: null })
		}
		if (path !== '/v1/threads/{thread_id}/branch') {
			return Promise.resolve({ data: null, error: null })
		}
		const query = options?.params?.query ?? {}
		branchQueries.push(query)
		const cursor = typeof query.cursor === 'string' ? query.cursor : null
		if (cursor && holdCursors.has(cursor)) {
			return new Promise((resolve) => heldPages.set(cursor, resolve))
		}
		// a three-message chain split across the window and its two neighbours,
		// so a page that lands really does extend the rendered branch
		const chain: Record<string, MessageFixture> = {
			'root-1': makeApiMessage({ id: 'm_root', thread_id: THREAD_ID, parent_id: null }),
			'leaf-1': makeApiMessage({ id: 'm_leaf', thread_id: THREAD_ID, parent_id: 'm_1' }),
		}
		const message =
			(cursor ? chain[cursor] : null) ??
			makeApiMessage({ id: 'm_1', thread_id: THREAD_ID, parent_id: 'm_root' })
		return Promise.resolve({ data: makeBranchPage([message]), error: null })
	})
}

/** count of `/branch` fetches that used a paging cursor. */
function pagedQueries(): Record<string, unknown>[] {
	return branchQueries.filter((query) => typeof query.cursor === 'string')
}

/** an opened thread parked mid-history, with a container of the given size. */
async function openThread(
	scrollHeight: number,
	clientHeight: number
): Promise<{ state: ChatState; container: FakeContainer }> {
	mockThread()
	const state = createChatState()
	await loadTree(THREAD_ID, state, { anchorMessageId: 'm_anchor' })
	const container = makeContainer(scrollHeight, clientHeight)
	state.scrollContainer = container.el
	state.hasLoadedBranch = true
	state.initialScrollDone = true
	return { state, container }
}

/** a scroll the app drove: the reveal parking the view, a page restore. */
function programmaticScrollTo(state: ChatState, container: FakeContainer, top: number): void {
	state.markProgrammaticScroll('auto')
	container.el.scrollTop = top
	state.handleScroll()
}

/** let the programmatic window lapse, so the next scroll counts as the reader's. */
function settleProgrammaticWindow(): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, 200))
}

/** a scroll the reader drove. */
function userScrollTo(state: ChatState, container: FakeContainer, top: number): void {
	state.onUserScrollGesture(top < container.el.scrollTop ? 'up' : 'down')
	container.el.scrollTop = top
	state.handleScroll()
}

describe('scroll paging', () => {
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

	it('pages neither direction when the opening scroll parks on an edge', async () => {
		const { state, container } = await openThread(3000, 1000)

		// the anchor reveal lands the view on the bottom edge of the window
		programmaticScrollTo(state, container, 2000)
		// and the top edge is inside its trigger the moment layout settles
		programmaticScrollTo(state, container, 0)

		await vi.waitFor(() => expect(state.isLoadingOlderMessages).toBe(false))
		expect(pagedQueries()).toHaveLength(0)
		expect(branchQueries).toHaveLength(1)
	})

	it('pages the direction the reader scrolled toward, and only that one', async () => {
		const { state, container } = await openThread(3000, 1000)

		userScrollTo(state, container, 1200)
		userScrollTo(state, container, 40)

		await vi.waitFor(() => expect(pagedQueries()).toHaveLength(1))
		expect(pagedQueries()[0]).toMatchObject({ cursor: 'root-1' })
	})

	it('pages when the reader pulls against an edge that cannot scroll', async () => {
		const { state, container } = await openThread(3000, 1000)
		// the open parks the view on the bottom edge and nothing pages by itself
		programmaticScrollTo(state, container, 2000)
		expect(pagedQueries()).toHaveLength(0)

		// a wheel against that edge moves nothing, so it fires no scroll event
		state.onUserScrollGesture('down')

		await vi.waitFor(() => expect(pagedQueries()).toHaveLength(1))
		expect(pagedQueries()[0]).toMatchObject({ cursor: 'leaf-1' })
	})

	it('renders the page a scroll-up fetched', async () => {
		const { state, container } = await openThread(3000, 1000)
		await settleProgrammaticWindow()
		const before = state.runBlocks.reduce((n, block) => n + block.items.length, 0)

		userScrollTo(state, container, 1200)
		userScrollTo(state, container, 40)
		await vi.waitFor(() => expect(pagedQueries()).toHaveLength(1))
		await vi.waitFor(() => expect(state.isLoadingOlderMessages).toBe(false))

		expect(state.messages.map((m) => m.id)).toEqual(['m_root', 'm_1'])
		expect(state.runBlocks.reduce((n, block) => n + block.items.length, 0)).toBe(before + 1)
	})

	it('never runs both directions at once', async () => {
		const { state, container } = await openThread(3000, 1000)
		holdCursors.add('root-1')

		userScrollTo(state, container, 1200)
		userScrollTo(state, container, 40)
		await vi.waitFor(() => expect(state.isLoadingOlderMessages).toBe(true))

		// the reader flings back to the bottom while the older page is still out
		userScrollTo(state, container, 2000)
		expect(state.isLoadingNewerMessages).toBe(false)
		expect(pagedQueries()).toHaveLength(1)

		heldPages.get('root-1')?.({ data: makeBranchPage([]), error: null })
		await vi.waitFor(() => expect(state.isLoadingOlderMessages).toBe(false))
		expect(pagedQueries()).toHaveLength(1)
	})

	it('ignores the scroll a page restore leaves behind', async () => {
		// barely taller than the viewport: both edges are in trigger range
		const { state, container } = await openThread(1600, 1500)
		programmaticScrollTo(state, container, 100)
		await settleProgrammaticWindow()

		userScrollTo(state, container, 0)
		await vi.waitFor(() => expect(pagedQueries()).toHaveLength(1))
		expect(pagedQueries()[0]).toMatchObject({ cursor: 'root-1' })
		await vi.waitFor(() => expect(state.isLoadingOlderMessages).toBe(false))

		// the prepended page restores the reader's offset, which is a jump toward
		// the bottom - and lands inside the bottom trigger on a short window
		container.setHeight(3100)
		programmaticScrollTo(state, container, 1500)
		expect(pagedQueries()).toHaveLength(1)
	})

	it('does not page back the other way when a landed page reflows the view', async () => {
		const { state, container } = await openThread(3000, 1000)
		await settleProgrammaticWindow()

		userScrollTo(state, container, 1200)
		userScrollTo(state, container, 1990)
		await vi.waitFor(() => expect(pagedQueries()).toHaveLength(1))
		expect(pagedQueries()[0]).toMatchObject({ cursor: 'leaf-1' })
		await vi.waitFor(() => expect(state.isLoadingNewerMessages).toBe(false))

		// the page rebuilt the branch shorter than it was, so the browser clamps
		// the reader onto the top edge - not an arrival, and not a page up
		container.setHeight(1000)
		container.el.scrollTop = 0
		state.handleScroll()
		expect(pagedQueries()).toHaveLength(1)
	})

	it('backfills a window shorter than the viewport, one direction at a time', async () => {
		const { state, container } = await openThread(700, 1000)
		// the page that lands fills the screen
		apiMocks.GET.mockImplementation((path: string, options?: ApiPathOptions) => {
			if (path !== '/v1/threads/{thread_id}/branch') {
				return Promise.resolve({ data: null, error: null })
			}
			branchQueries.push(options?.params?.query ?? {})
			container.setHeight(2400)
			return Promise.resolve({ data: makeBranchPage([]), error: null })
		})

		state.onContentResize()

		await vi.waitFor(() => expect(pagedQueries()).toHaveLength(1))
		// toward the leaf: it appends below the reader instead of above them
		expect(pagedQueries()[0]).toMatchObject({ cursor: 'leaf-1' })
		await vi.waitFor(() => expect(state.isLoadingNewerMessages).toBe(false))
		state.onContentResize()
		expect(pagedQueries()).toHaveLength(1)
	})

	it('stops backfilling when a page adds no height', async () => {
		const { state, container } = await openThread(700, 1000)
		expect(container.height()).toBe(700)

		state.onContentResize()

		await vi.waitFor(() => expect(pagedQueries()).toHaveLength(1))
		await vi.waitFor(() => expect(state.isLoadingNewerMessages).toBe(false))
		expect(pagedQueries()).toHaveLength(1)
	})
})
