import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread, resetIdCounter } from './fixtures'

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
		forgetRun: vi.fn(),
	},
}))

vi.mock('$lib/stores/agents.svelte', () => ({
	agents: {
		list: [],
		load: vi.fn(),
	},
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		isLoggedIn: false,
		currentUser: null,
	},
}))

import { createChatState } from '$lib/chat/createChatState.svelte'
import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { chat } from '$lib/stores/chat.svelte'

function deferredResponse<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
	let resolve: (value: T) => void = () => {}
	const promise = new Promise<T>((res) => {
		resolve = res
	})
	return { promise, resolve }
}

describe('createChatState steering queue reconciliation', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.POST.mockReset()
		apiMocks.PATCH.mockReset()
		apiMocks.DELETE.mockReset()
		vi.mocked(activeRunsStore.forgetRun).mockClear()
	})

	afterEach(() => {
		chat.clear()
	})

	it('does not drop a pending steering message after message.created confirms it', async () => {
		const state = createChatState()
		state.setThread(makeThread({ id: 'thread_1' }))
		const response = deferredResponse<{
			data: { message_id: string; state: 'queued' }
			error: null
		}>()
		apiMocks.POST.mockReturnValueOnce(response.promise)

		state.stageQueuedSteeringMessage({
			id: 'local-steering-1',
			clientSteeringId: 'local-steering-1',
			runId: 'run_1',
			content: [],
			text: 'steer me',
			attachments: [],
			createdAt: new Date('2026-05-16T10:00:00.000Z'),
			message: null,
			deliveryState: 'sending',
			input: { text: 'steer me' },
		})

		const flush = state.flushPendingSteeringMessages('run_1', 'parent_1')
		expect(apiMocks.POST).toHaveBeenCalledWith('/v1/runs/{run_id}/steer', {
			params: { path: { run_id: 'run_1' } },
			body: {
				input: { text: 'steer me' },
				parent_id: 'parent_1',
				client_steering_id: 'local-steering-1',
			},
		})

		state.confirmQueuedSteeringMessage(
			'local-steering-1',
			'server_1',
			'run_1',
			makeApiMessage({
				id: 'server_1',
				thread_id: 'thread_1',
				metadata_: {
					steering_state: 'queued',
					run_id: 'run_1',
					client_steering_id: 'local-steering-1',
				},
			})
		)

		response.resolve({ data: { message_id: 'server_1', state: 'queued' }, error: null })
		await flush

		expect(apiMocks.DELETE).not.toHaveBeenCalled()
		expect(state.queuedSteeringMessages).toHaveLength(1)
		expect(state.queuedSteeringMessages[0]).toMatchObject({
			id: 'server_1',
			clientSteeringId: 'local-steering-1',
			deliveryState: 'queued',
		})
	})

	it('quietly clears pending steering when the run has already ended', async () => {
		const state = createChatState()
		state.setThread(makeThread({ id: 'thread_1' }))
		const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
		apiMocks.POST.mockResolvedValueOnce({
			data: null,
			error: { detail: 'run not found' },
		})

		state.stageQueuedSteeringMessage({
			id: 'local-steering-1',
			clientSteeringId: 'local-steering-1',
			runId: 'run_ended',
			content: [],
			text: 'too late',
			attachments: [],
			createdAt: new Date('2026-05-17T01:51:09.000Z'),
			message: null,
			deliveryState: 'sending',
			input: { text: 'too late' },
		})

		try {
			await state.flushPendingSteeringMessages('run_ended', 'parent_1')
		} finally {
			consoleError.mockRestore()
		}

		expect(activeRunsStore.forgetRun).toHaveBeenCalledWith('run_ended')
		expect(consoleError).not.toHaveBeenCalled()
		expect(apiMocks.DELETE).not.toHaveBeenCalled()
		expect(state.queuedSteeringMessages).toHaveLength(0)
	})
})
