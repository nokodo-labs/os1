/**
 * tests for the typing contract, both ends: the composer's outgoing signal
 * (heartbeat cadence, every draft change, when it stops) and the ChatStore
 * tracker that lists who is composing until their signals stop arriving.
 *
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { createTypingSignal, TYPING_HEARTBEAT_MS } from '$lib/chat/typingSignal'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeStreamMessage } from './fixtures'

let capturedHandler: ((msg: unknown) => void) | null = null

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribe: vi.fn((handler: (msg: unknown) => void) => {
			capturedHandler = handler
			return () => {
				capturedHandler = null
			}
		}),
		subscribeTypes: vi.fn((_types: readonly string[], handler: (msg: unknown) => void) => {
			capturedHandler = handler
			return () => {
				capturedHandler = null
			}
		}),
	},
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: null, error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
	getApiBaseUrl: vi.fn(() => 'http://localhost:1383'),
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/auth/jwt', () => ({
	getJwtUserId: vi.fn(() => 'user_me'),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: { init: vi.fn(), cleanup: vi.fn() },
}))

import { chat } from '$lib/stores/chat.svelte'

function dispatch(msg: unknown): void {
	if (!capturedHandler) throw new Error('no handler registered - did you call chat.init()?')
	capturedHandler(msg)
}

function startTyping(threadId: string, userId: string, type = 'typing.start'): void {
	dispatch(makeStreamMessage(type, { thread_id: threadId, user_id: userId }))
}

describe('ChatStore typing signals', () => {
	beforeEach(() => {
		vi.useFakeTimers()
		chat.clear()
		chat.init()
	})

	afterEach(() => {
		chat.cleanup()
		chat.clear()
		vi.useRealTimers()
		capturedHandler = null
	})

	it('lists somebody who started composing', () => {
		startTyping('thread_1', 'user_ada')

		expect(chat.composingUserIds('thread_1')).toEqual(['user_ada'])
		expect(chat.composingUserIds('thread_2')).toEqual([])
	})

	it('accepts the typing.user.* spelling of the same signal', () => {
		startTyping('thread_1', 'user_ada', 'typing.user.start')
		expect(chat.composingUserIds('thread_1')).toEqual(['user_ada'])

		dispatch(
			makeStreamMessage('typing.user.stop', { thread_id: 'thread_1', user_id: 'user_ada' })
		)
		expect(chat.composingUserIds('thread_1')).toEqual([])
	})

	it('drops a composer as soon as they stop', () => {
		startTyping('thread_1', 'user_ada')
		dispatch(makeStreamMessage('typing.stop', { thread_id: 'thread_1', user_id: 'user_ada' }))

		expect(chat.composingUserIds('thread_1')).toEqual([])
		expect(chat.composingUsers.has('thread_1')).toBe(false)
	})

	it('expires a signal that stops arriving', () => {
		startTyping('thread_1', 'user_ada')

		vi.advanceTimersByTime(7999)
		expect(chat.composingUserIds('thread_1')).toEqual(['user_ada'])

		vi.advanceTimersByTime(1)
		expect(chat.composingUserIds('thread_1')).toEqual([])
	})

	it('keeps a composer alive while they keep signalling', () => {
		startTyping('thread_1', 'user_ada')

		// the composer re-signals every 3s; each one pushes the expiry out
		for (let i = 0; i < 5; i += 1) {
			vi.advanceTimersByTime(3000)
			startTyping('thread_1', 'user_ada')
		}

		vi.advanceTimersByTime(3000)
		expect(chat.composingUserIds('thread_1')).toEqual(['user_ada'])

		vi.advanceTimersByTime(8000)
		expect(chat.composingUserIds('thread_1')).toEqual([])
	})

	it('tracks several composers per thread, and threads apart', () => {
		startTyping('thread_1', 'user_ada')
		vi.advanceTimersByTime(4000)
		startTyping('thread_1', 'user_bob')
		startTyping('thread_2', 'user_bob')

		expect(chat.composingUserIds('thread_1')).toEqual(['user_ada', 'user_bob'])

		// ada's older signal expires on its own without touching bob's
		vi.advanceTimersByTime(4000)
		expect(chat.composingUserIds('thread_1')).toEqual(['user_bob'])
		expect(chat.composingUserIds('thread_2')).toEqual(['user_bob'])
	})

	it('never tracks your own composing', () => {
		startTyping('thread_1', 'user_me')

		expect(chat.composingUserIds('thread_1')).toEqual([])
	})

	it('ignores a signal that names no person', () => {
		// agents do not compose - they run, and generation has its own UI
		dispatch(makeStreamMessage('typing.start', { thread_id: 'thread_1', agent_id: 'agent_1' }))
		dispatch(makeStreamMessage('typing.start', { user_id: 'user_ada' }))

		expect(chat.composingUserIds('thread_1')).toEqual([])
	})

	it('forgets every composer when the store is cleared', () => {
		startTyping('thread_1', 'user_ada')
		chat.clear()

		expect(chat.composingUsers.size).toBe(0)
		expect(chat.composingUserIds('thread_1')).toEqual([])
	})

	it('stays listed while the composer signal keeps beating', () => {
		// the sender's own signal drives the receiver: a composer who never stops
		// editing must never blink out, which is what F125 fixed.
		const signal = createTypingSignal((typing) =>
			dispatch(
				makeStreamMessage(typing ? 'typing.start' : 'typing.stop', {
					thread_id: 'thread_1',
					user_id: 'user_ada',
				})
			)
		)

		// typed in, then partly deleted again: both are composer activity
		for (const draft of ['h', 'he', 'hel', 'hell', 'hello', 'hell', 'hel', 'he']) {
			signal.update(draft, true)
			vi.advanceTimersByTime(2000)
			expect(chat.composingUserIds('thread_1')).toEqual(['user_ada'])
		}

		// a long think mid-message is still composing: the heartbeat carries it
		vi.advanceTimersByTime(20000)
		expect(chat.composingUserIds('thread_1')).toEqual(['user_ada'])

		signal.update('', true)
		expect(chat.composingUserIds('thread_1')).toEqual([])
	})
})

describe('composer typing signal', () => {
	let sent: boolean[]

	beforeEach(() => {
		vi.useFakeTimers()
		sent = []
	})

	afterEach(() => {
		vi.useRealTimers()
	})

	const signal = () => createTypingSignal((typing) => sent.push(typing))

	it('signals immediately, then heartbeats inside the receiver TTL', () => {
		const typing = signal()
		typing.update('h', true)
		expect(sent).toEqual([true])

		vi.advanceTimersByTime(TYPING_HEARTBEAT_MS)
		expect(sent).toEqual([true, true])

		// four beats in 12s: comfortably under the receiver's 8s expiry
		vi.advanceTimersByTime(TYPING_HEARTBEAT_MS * 3)
		expect(sent.filter(Boolean)).toHaveLength(5)
		expect(sent).not.toContain(false)
	})

	it('keeps signalling through deletions, not only insertions', () => {
		const typing = signal()
		for (const draft of ['hello', 'hell', 'hel', 'he', 'h']) {
			typing.update(draft, true)
			vi.advanceTimersByTime(1000)
		}

		// five edits inside 5s, so the cadence stays the heartbeat's, not one
		// event per keystroke - and nothing has stopped
		expect(sent).not.toContain(false)
		expect(sent).toHaveLength(2)
	})

	it('stops the moment the draft is cleared', () => {
		const typing = signal()
		typing.update('hello', true)
		typing.update('', true)

		expect(sent).toEqual([true, false])

		vi.advanceTimersByTime(TYPING_HEARTBEAT_MS * 4)
		expect(sent).toEqual([true, false])
	})

	it('stops when the composer blurs with text still in the box', () => {
		const typing = signal()
		typing.update('hello', true)
		typing.update('hello', false)

		expect(sent).toEqual([true, false])
	})

	it('stops on teardown, and only when it had started', () => {
		const typing = signal()
		typing.stop()
		expect(sent).toEqual([])

		typing.update('hello', true)
		typing.stop()
		typing.stop()
		expect(sent).toEqual([true, false])
	})

	it('never signals for an empty or whitespace draft', () => {
		const typing = signal()
		typing.update('', true)
		typing.update('   \n', true)
		vi.advanceTimersByTime(TYPING_HEARTBEAT_MS * 3)

		expect(sent).toEqual([])
	})
})
