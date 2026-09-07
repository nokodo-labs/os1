/**
 * tests for the bottom pin across a viewport resize.
 *
 * the virtual keyboard resizes the transcript itself now
 * (`interactive-widget=resizes-content`): the browser clamps `scrollTop` and
 * fires the scroll event for it in the same frame as the resize, and the
 * composer's keyboard padding swap grows the transcript back a frame later. the
 * chat page arms `markProgrammaticScroll` from the resize listener and re-lands
 * on the bottom through the settle - these cover the guard that makes that work.
 *
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

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
import { computeIsAtBottom } from '$lib/chat/helpers'
import type { ChatState } from '$lib/chat/types'
import { chat } from '$lib/stores/chat.svelte'

interface Transcript {
	el: HTMLElement
	/** the viewport resizing under the transcript, clamping `scrollTop` like a browser. */
	resizeViewport(clientHeight: number): void
	/** the composer's keyboard padding swap growing the transcript back. */
	growPadding(px: number): void
	distanceToBottom(): number
}

/** a transcript whose geometry the test drives, with the browser's own clamp. */
function makeTranscript(scrollHeight: number, clientHeight: number): Transcript {
	const el = document.createElement('div')
	let height = scrollHeight
	let client = clientHeight
	let top = 0
	const clamp = (next: number) => Math.max(0, Math.min(next, height - client))

	Object.defineProperty(el, 'scrollHeight', { configurable: true, get: () => height })
	Object.defineProperty(el, 'clientHeight', { configurable: true, get: () => client })
	Object.defineProperty(el, 'scrollTop', {
		configurable: true,
		get: () => top,
		set: (next: number) => {
			top = clamp(next)
		},
	})
	Object.defineProperty(el, 'scrollTo', {
		configurable: true,
		value: (options: ScrollToOptions) => {
			top = clamp(options.top ?? top)
		},
	})

	return {
		el,
		resizeViewport(next: number) {
			client = next
			top = clamp(top)
		},
		growPadding(px: number) {
			height += px
		},
		distanceToBottom: () => height - top - client,
	}
}

/** a transcript pinned to its bottom, keyboard up. */
function pinnedWithKeyboard(): { state: ChatState; transcript: Transcript } {
	const state = createChatState()
	const transcript = makeTranscript(3000, 700)
	transcript.el.scrollTop = 3000
	state.scrollContainer = transcript.el
	state.autoScroll = true
	return { state, transcript }
}

/** let the programmatic window lapse, so the next scroll counts as the reader's. */
function settleProgrammaticWindow(): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, 200))
}

describe('bottom pin across a viewport resize', () => {
	beforeEach(() => {
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.POST.mockReset()
	})

	it('keeps the pin when the keyboard closing clamps the scroll', () => {
		const { state, transcript } = pinnedWithKeyboard()

		// the page arms the suppression from the resize event, which the browser
		// dispatches BEFORE the scroll event the clamp produces
		state.markProgrammaticScroll('auto')
		transcript.resizeViewport(1000)
		state.handleScroll()

		expect(state.autoScroll).toBe(true)

		// the composer's padding comes back a frame later - that alone leaves the
		// view short of the bottom, with no scroll event left to correct it
		transcript.growPadding(16)
		expect(transcript.distanceToBottom()).toBe(16)

		// the settle hold re-lands on the exact bottom while the pin is on
		state.scrollToBottom('auto')
		expect(computeIsAtBottom(transcript.el)).toBe(true)
		expect(transcript.distanceToBottom()).toBe(0)
	})

	it('would drop the pin on an unsuppressed resize scroll', () => {
		const { state, transcript } = pinnedWithKeyboard()

		// the keyboard opening: the transcript shrinks under a scroll position that
		// stays put, so the view is suddenly 300px off the bottom
		transcript.resizeViewport(400)
		state.handleScroll()

		expect(transcript.distanceToBottom()).toBe(300)
		expect(state.autoScroll).toBe(false)
	})

	it('holds the pin through a whole run of resize scroll events', () => {
		const { state, transcript } = pinnedWithKeyboard()

		// android fires viewport events all the way through the keyboard animation
		for (const clientHeight of [760, 820, 900, 1000]) {
			state.markProgrammaticScroll('auto')
			transcript.resizeViewport(clientHeight)
			state.handleScroll()
			state.scrollToBottom('auto')
		}

		expect(state.autoScroll).toBe(true)
		expect(computeIsAtBottom(transcript.el)).toBe(true)
	})

	it('still lets the reader detach mid-settle', () => {
		const { state, transcript } = pinnedWithKeyboard()

		state.markProgrammaticScroll('auto')
		transcript.resizeViewport(1000)
		// a genuine upward gesture bypasses the window entirely
		state.onUserScrollGesture('up')
		transcript.el.scrollTop = 1200
		state.handleScroll()

		expect(state.autoScroll).toBe(false)
	})

	it('stops suppressing once the settle window has lapsed', async () => {
		const { state, transcript } = pinnedWithKeyboard()

		state.markProgrammaticScroll('auto')
		transcript.resizeViewport(1000)
		state.handleScroll()
		await settleProgrammaticWindow()

		// long after the resize, scrolling away is the reader again
		transcript.el.scrollTop = 1200
		state.handleScroll()

		expect(state.autoScroll).toBe(false)
	})
})
