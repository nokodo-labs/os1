/**
 * the projects cache must not turn lifecycle invalidation into a poll.
 *
 * the chat sidebar calls `projects.load()` from an `$effect`. the cache stamp
 * is reactive state, so a plain read there subscribed the effect to it and
 * every `invalidate()` (ws drop, visibility change, execution gap) re-ran the
 * effect straight back into the API.
 */

import type { components } from '$lib/api/types'
import { flushSync } from 'svelte'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Project = components['schemas']['Project']

let listCalls = 0

vi.mock('$app/environment', () => ({ browser: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn((path: string) => {
			if (path === '/v1/projects') {
				listCalls += 1
				return Promise.resolve({ data: [makeProject('proj_1')], error: null })
			}
			return Promise.resolve({ data: null, error: null })
		}),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/notifications.svelte', () => ({ showError: vi.fn() }))

vi.mock('$lib/stores/storeEvents', () => ({
	STORE_EVENT_TYPES: {
		projects: ['project.created'],
		resourceAccessResource: [],
		projectCounts: [],
	},
	subscribeToStoreEvents: vi.fn(() => () => {}),
}))

const { projects } = await import('$lib/stores/projects.svelte')

function makeProject(id: string): Project {
	return {
		id,
		name: id,
		description: '',
		owner_id: 'user_me',
		thread_ids: [],
		created_at: '2026-08-29T00:00:00Z',
		updated_at: '2026-08-29T00:00:00Z',
	} as Project
}

/** let pending effects and the in-flight request both settle */
async function settle(): Promise<void> {
	flushSync()
	await new Promise((resolve) => setTimeout(resolve, 0))
	flushSync()
	await new Promise((resolve) => setTimeout(resolve, 0))
	flushSync()
}

describe('projects.load() from an effect', () => {
	beforeEach(() => {
		listCalls = 0
		projects.clear()
	})

	it('loads once and does not refetch when the lifecycle marks it stale', async () => {
		const cleanup = $effect.root(() => {
			$effect(() => {
				void projects.load()
			})
		})

		await settle()
		expect(listCalls).toBe(1)

		projects.invalidate()
		await settle()

		expect(listCalls).toBe(1)
		cleanup()
	})

	it('still refetches when a caller asks for it after invalidation', async () => {
		await projects.load()
		expect(listCalls).toBe(1)

		projects.invalidate()
		await projects.load()

		expect(listCalls).toBe(2)
	})
})
