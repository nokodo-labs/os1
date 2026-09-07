/**
 * a run that stops emitting text is still running, so the text placeholder
 * comes back at the end of what is written until the next token lands.
 * uses .svelte.test.ts so Svelte 5 runes work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribe: vi.fn(() => () => {}),
		subscribeTypes: vi.fn(() => () => {}),
	},
}))

vi.mock('$lib/api/client', () => ({
	api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
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
import type { ChatState, StreamingAssistantState } from '$lib/chat/types'

/** the threshold the state factory watches, mirrored so the test names it. */
const STALL_MS = 2000

function streaming(messageId: string, content = ''): StreamingAssistantState {
	return {
		runId: 'run_1',
		messageId,
		content,
		timestamp: new Date(),
		senderAgentId: 'agent_1',
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
}

function startStreaming(state: ChatState, messageId = 'm1'): void {
	state.streamingAssistant = streaming(messageId)
	state.appendStreamingText('half an answer')
}

describe('streaming text stall', () => {
	beforeEach(() => {
		vi.useFakeTimers()
	})

	afterEach(() => {
		vi.useRealTimers()
	})

	it('stays quiet while tokens keep arriving', () => {
		const state = createChatState()
		startStreaming(state)

		vi.advanceTimersByTime(STALL_MS - 1)
		expect(state.isStreamingTextStalled).toBe(false)

		state.appendStreamingText(' and more')
		vi.advanceTimersByTime(STALL_MS - 1)
		expect(state.isStreamingTextStalled).toBe(false)
	})

	it('reports a stall once the stream goes quiet mid-answer', () => {
		const state = createChatState()
		startStreaming(state)

		vi.advanceTimersByTime(STALL_MS)

		expect(state.isStreamingTextStalled).toBe(true)
	})

	it('clears the moment the next token lands', () => {
		const state = createChatState()
		startStreaming(state)
		vi.advanceTimersByTime(STALL_MS)

		state.appendStreamingText(' back again')

		expect(state.isStreamingTextStalled).toBe(false)
	})

	it('never reports a stall for a stream that already ended', () => {
		const state = createChatState()
		startStreaming(state)
		state.streamingAssistant = null

		vi.advanceTimersByTime(STALL_MS * 2)

		expect(state.isStreamingTextStalled).toBe(false)
	})

	it('does not carry a stall across to the next bubble', () => {
		const state = createChatState()
		startStreaming(state)
		vi.advanceTimersByTime(STALL_MS)
		expect(state.isStreamingTextStalled).toBe(true)

		state.streamingAssistant = streaming('m2')

		expect(state.isStreamingTextStalled).toBe(false)
	})
})
