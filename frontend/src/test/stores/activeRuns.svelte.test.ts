/**
 * tests for active run websocket handling.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

let capturedHandler: ((msg: unknown) => void) | null = null

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
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
		GET: vi.fn().mockResolvedValue({ data: [], error: null }),
	},
}))

import { activeRunsStore } from '$lib/stores/activeRuns.svelte'

function dispatch(msg: unknown): void {
	if (!capturedHandler) throw new Error('no handler registered')
	capturedHandler(msg)
}

describe('ActiveRunsStore websocket handling', () => {
	beforeEach(() => {
		activeRunsStore.cleanup()
		activeRunsStore.init()
	})

	afterEach(() => {
		activeRunsStore.cleanup()
		capturedHandler = null
	})

	it('marks global and thread state running when a run starts', () => {
		dispatch({
			type: 'run.started',
			data: { thread_id: 'thread_1', run_id: 'run_1', agent_id: 'agent_1' },
		})

		expect(activeRunsStore.state).toBe('running')
		expect(activeRunsStore.hasActiveRuns('thread_1')).toBe(true)
		expect(activeRunsStore.getRunsForThread('thread_1')).toHaveLength(1)
	})

	it('loads and clears active runs from catch-up events', () => {
		dispatch({
			type: 'runs.active',
			data: [{ thread_id: 'thread_1', run_id: 'run_1', agent_id: 'agent_1' }],
		})

		expect(activeRunsStore.state).toBe('running')
		expect(activeRunsStore.hasActiveRuns('thread_1')).toBe(true)

		dispatch({ type: 'runs.active', data: [] })

		expect(activeRunsStore.state).toBe('idle')
		expect(activeRunsStore.hasActiveRuns('thread_1')).toBe(false)
	})

	it('clears a run on completion', () => {
		dispatch({
			type: 'run.started',
			data: { thread_id: 'thread_1', run_id: 'run_1', agent_id: 'agent_1' },
		})
		dispatch({ type: 'run.completed', data: { thread_id: 'thread_1', run_id: 'run_1' } })

		expect(activeRunsStore.state).toBe('idle')
		expect(activeRunsStore.hasActiveRuns('thread_1')).toBe(false)
	})

	it('goes red when a run actually fails', () => {
		dispatch({
			type: 'run.started',
			data: { thread_id: 'thread_1', run_id: 'run_1', agent_id: 'agent_1' },
		})
		dispatch({
			type: 'run.error',
			data: { thread_id: 'thread_1', run_id: 'run_1', reason: 'provider_error' },
		})

		expect(activeRunsStore.state).toBe('error')
	})

	it('ignores a run that names no thread', () => {
		// inline explain/ask runs are ephemeral and thread-less on purpose: no
		// transcript may resume them, no sidebar row may light up for them, and
		// their failure is nobody's conversation.
		dispatch({ type: 'run.started', data: { run_id: 'run_inline', agent_id: 'agent_1' } })
		dispatch({ type: 'runs.active', data: [{ run_id: 'run_inline', agent_id: 'agent_1' }] })

		expect(activeRunsStore.runs.size).toBe(0)
		expect(activeRunsStore.activeThreadIds).toEqual([])
		expect(activeRunsStore.state).toBe('idle')

		dispatch({ type: 'run.error', data: { run_id: 'run_inline', reason: 'provider_error' } })

		expect(activeRunsStore.state).toBe('idle')
	})

	it('settles quietly when the reader stopped the run', () => {
		dispatch({
			type: 'run.started',
			data: { thread_id: 'thread_1', run_id: 'run_1', agent_id: 'agent_1' },
		})
		dispatch({
			type: 'run.error',
			data: { thread_id: 'thread_1', run_id: 'run_1', reason: 'cancelled' },
		})

		// the run is over because the user ended it - nothing failed.
		expect(activeRunsStore.state).toBe('idle')
		expect(activeRunsStore.hasActiveRuns('thread_1')).toBe(false)
	})
})
