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
})
