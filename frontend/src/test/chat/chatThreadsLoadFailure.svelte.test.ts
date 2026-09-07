/**
 * a failed thread-list fetch must never present as an endless sidebar skeleton.
 *
 * `refreshThreads()` returned silently on error, so the sidebar - which gated
 * its skeleton on `!hasLoaded` alone - kept shimmering forever. the store now
 * keeps the prior threads, leaves `hasLoaded` alone, and surfaces `error`.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeThread, resetIdCounter } from './fixtures'

let failing = false

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn((path: string) => {
			if (path === '/v1/threads') {
				return failing
					? Promise.resolve({ data: undefined, error: { detail: 'offline' } })
					: Promise.resolve({
							data: [makeThread({ id: 'thread_listed' })],
							error: undefined,
						})
			}
			return Promise.resolve({ data: [], error: undefined })
		}),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
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

vi.mock('$lib/stores/storeEvents', () => ({
	STORE_EVENT_TYPES: {
		chat: ['thread.created'],
		resourceAccessResource: ['access.updated'],
		typing: ['typing.start'],
	},
	subscribeToStoreEvents: vi.fn(() => () => {}),
}))

const { chat } = await import('$lib/stores/chat.svelte')

describe('chat.refreshThreads() failure handling', () => {
	beforeEach(() => {
		resetIdCounter()
		failing = false
		chat.clear()
	})

	it('keeps the loaded list and reports the error when a refresh fails', async () => {
		await chat.refreshThreads()
		expect(chat.recentThreads).toHaveLength(1)
		expect(chat.hasLoaded).toBe(true)

		failing = true
		await chat.refreshThreads()

		expect(chat.recentThreads).toHaveLength(1)
		expect(chat.hasLoaded).toBe(true)
		expect(chat.error).toBe('failed to load chats')
	})

	it('does not mark itself loaded when the first fetch fails', async () => {
		failing = true
		await chat.refreshThreads()

		expect(chat.hasLoaded).toBe(false)
		expect(chat.recentThreads).toHaveLength(0)
		expect(chat.error).toBe('failed to load chats')
	})

	it('recovers on the next successful load', async () => {
		failing = true
		await chat.refreshThreads()
		expect(chat.error).toBe('failed to load chats')

		failing = false
		await chat.refreshThreads()

		expect(chat.error).toBeNull()
		expect(chat.hasLoaded).toBe(true)
		expect(chat.recentThreads).toHaveLength(1)
	})

	it('clears the error signal on logout', async () => {
		failing = true
		await chat.refreshThreads()
		expect(chat.error).toBe('failed to load chats')

		chat.clear()

		expect(chat.error).toBeNull()
		expect(chat.hasLoaded).toBe(false)
	})
})
