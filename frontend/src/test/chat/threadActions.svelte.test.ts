import { deleteThread, setThreadMuted } from '$lib/chat/threadActions'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
	del: vi.fn(),
	patch: vi.fn(),
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn(),
		POST: vi.fn(),
		PATCH: apiMocks.patch,
		DELETE: apiMocks.del,
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/auth/jwt', () => ({
	getJwtUserId: vi.fn(() => 'user_me'),
}))

describe('deleteThread', () => {
	beforeEach(() => {
		apiMocks.del.mockReset()
		apiMocks.del.mockResolvedValue({ response: { status: 204 }, error: undefined })
	})

	it('omits the originated-resources param by default', async () => {
		await deleteThread('thread_1')

		const params = apiMocks.del.mock.calls.at(-1)?.[1].params
		expect(params.path).toEqual({ thread_id: 'thread_1' })
		expect(params.query).toBeUndefined()
	})

	it('sends the originated-resources param when opted in', async () => {
		await deleteThread('thread_1', { deleteOriginatedResources: true })

		const params = apiMocks.del.mock.calls.at(-1)?.[1].params
		expect(params.query).toEqual({ delete_originated_resources: true })
	})
})

describe('setThreadMuted', () => {
	beforeEach(() => {
		apiMocks.patch.mockReset()
	})

	it('addresses the participant row of the calling user', async () => {
		apiMocks.patch.mockResolvedValue({ data: { thread_id: 'thread_1', muted: true } })

		const result = await setThreadMuted('thread_1', true)

		const call = apiMocks.patch.mock.calls.at(-1)
		expect(call?.[0]).toBe('/v1/threads/{thread_id}/participants/users/{user_id}')
		expect(call?.[1].params.path).toEqual({ thread_id: 'thread_1', user_id: 'user_me' })
		expect(call?.[1].body).toEqual({ muted: true })
		expect(result).toBe(true)
	})

	it('returns the flag the server reports, not the requested one', async () => {
		apiMocks.patch.mockResolvedValue({ data: { thread_id: 'thread_1', muted: false } })

		expect(await setThreadMuted('thread_1', true)).toBe(false)
	})

	it('returns null when the write fails', async () => {
		apiMocks.patch.mockResolvedValue({ error: { detail: 'nope' } })

		expect(await setThreadMuted('thread_1', false)).toBeNull()
	})
})
