import { processDelta } from '$lib/chat/streamProcessor'
import type { ChatContext, StreamDeltaContext } from '$lib/chat/types'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage } from './fixtures'

const activeRunsMocks = vi.hoisted(() => ({
	forgetRun: vi.fn(),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: {
		forgetRun: activeRunsMocks.forgetRun,
	},
}))

function makeDelta(message = makeApiMessage()) {
	return {
		event: 'message_created',
		data: message,
	} as Parameters<typeof processDelta>[0]
}

describe('processDelta steering reconciliation', () => {
	beforeEach(() => {
		activeRunsMocks.forgetRun.mockReset()
	})

	it('confirms queued steering messages by client id from SSE message.created', () => {
		const confirmQueuedSteeringMessage = vi.fn(() => true)
		const stageQueuedSteeringMessage = vi.fn()
		const ctx = {
			confirmQueuedSteeringMessage,
			stageQueuedSteeringMessage,
		} as unknown as ChatContext
		const msg = makeApiMessage({
			id: 'msg_server_1',
			type: 'user',
			metadata_: {
				steering_state: 'queued',
				run_id: 'run_1',
				client_steering_id: 'local-steering-1',
			},
		})

		const result = processDelta(makeDelta(msg), {} as StreamDeltaContext, ctx)

		expect(result).toBe('continue')
		expect(confirmQueuedSteeringMessage).toHaveBeenCalledWith(
			'local-steering-1',
			'msg_server_1',
			'run_1',
			msg
		)
		expect(stageQueuedSteeringMessage).not.toHaveBeenCalled()
	})

	it('stages queued steering messages when SSE has no matching client id', () => {
		const confirmQueuedSteeringMessage = vi.fn(() => false)
		const stageQueuedSteeringMessage = vi.fn()
		const ctx = {
			confirmQueuedSteeringMessage,
			stageQueuedSteeringMessage,
		} as unknown as ChatContext
		const msg = makeApiMessage({
			id: 'msg_server_2',
			type: 'user',
			metadata_: {
				steering_state: 'queued',
				run_id: 'run_1',
			},
		})

		processDelta(makeDelta(msg), {} as StreamDeltaContext, ctx)

		expect(confirmQueuedSteeringMessage).not.toHaveBeenCalled()
		expect(stageQueuedSteeringMessage).toHaveBeenCalledWith(
			expect.objectContaining({ id: 'msg_server_2', runId: 'run_1', message: msg })
		)
	})

	it('forgets the active run when the stream emits the agent done sentinel', () => {
		const ctx = {} as ChatContext

		const result = processDelta(
			{
				event: 'delta',
				data: {
					run_id: 'run_done',
					agent_id: 'agent_1',
					message_id: null,
					parent_id: null,
					delta: { done: true },
				},
			},
			{} as StreamDeltaContext,
			ctx
		)

		expect(result).toBe('done')
		expect(activeRunsMocks.forgetRun).toHaveBeenCalledWith('run_done')
	})
})
