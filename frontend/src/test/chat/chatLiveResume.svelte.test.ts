/**
 * what the chat store re-reads when the websocket reconnects after a gap.
 *
 * the resume path reaches this store through the cache registry, whose entry
 * gates on `hasLoaded` and calls `refresh()`. the lifecycle only marks caches
 * stale, so nothing on screen updates unless `refresh()` reads it back.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeThread, resetIdCounter } from './fixtures'

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
		subscribePrefixes: vi.fn(() => () => {}),
		onStatusChange: vi.fn(() => () => {}),
	},
}))

vi.mock('$lib/api/client', () => ({
	api: apiMocks,
	getApiBaseUrl: vi.fn(() => 'http://localhost:1383'),
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/auth/jwt', () => ({
	getJwtUserId: vi.fn(() => 'user_test'),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: { init: vi.fn(), cleanup: vi.fn() },
}))

import { apiCacheStores } from '$lib/stores/apiCacheRegistry'
import { refreshLifecycleStores } from '$lib/stores/cacheLifecycle'
import { chat } from '$lib/stores/chat.svelte'

const chatEntry = apiCacheStores.filter((store) => store.id === 'chat')

function pathsCalled(path: string): number {
	return apiMocks.GET.mock.calls.filter((call) => call[0] === path).length
}

describe('chat.refresh() on reconnect after a live-stream gap', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		apiMocks.GET.mockReset()
		apiMocks.POST.mockReset()
		apiMocks.PATCH.mockReset()
		apiMocks.GET.mockImplementation((path: string) => {
			if (path === '/v1/threads') return Promise.resolve({ data: [], error: null })
			if (path === '/v1/threads/unread-counts/{user_id}') {
				return Promise.resolve({ data: [], error: null })
			}
			return Promise.resolve({ data: null, error: null })
		})
	})

	it('reads the sidebar list and its badges back, and signals the open thread', async () => {
		chat.recentThreads = [makeThread({ id: 't1' })]
		const versionBefore = chat.refreshVersion

		await chat.refresh()

		expect(pathsCalled('/v1/threads')).toBe(1)
		expect(pathsCalled('/v1/threads/unread-counts/{user_id}')).toBeGreaterThanOrEqual(1)
		// the thread page watches this and reloads its own branch window
		expect(chat.refreshVersion).toBe(versionBefore + 1)
	})

	it('does not re-read every cached thread', async () => {
		for (const id of ['t1', 't2', 't3']) {
			chat.threadCache.set(makeThread({ id }))
		}
		chat.invalidate()

		await chat.refresh()

		expect(pathsCalled('/v1/threads/{thread_id}')).toBe(0)
		expect(pathsCalled('/v1/threads/{thread_id}/branch')).toBe(0)
	})

	it('refreshes the badges even before the sidebar list has loaded', async () => {
		await chat.refresh()

		expect(pathsCalled('/v1/threads')).toBe(0)
		expect(pathsCalled('/v1/threads/unread-counts/{user_id}')).toBe(1)
	})

	it('is reached through the registry, and only once something has read it', async () => {
		expect(chatEntry).toHaveLength(1)

		// nothing has loaded the store yet: the resume path leaves it alone
		await refreshLifecycleStores(chatEntry)
		expect(apiMocks.GET).not.toHaveBeenCalled()

		chat.hasLoaded = true
		await refreshLifecycleStores(chatEntry)
		expect(pathsCalled('/v1/threads/unread-counts/{user_id}')).toBe(1)
	})
})
