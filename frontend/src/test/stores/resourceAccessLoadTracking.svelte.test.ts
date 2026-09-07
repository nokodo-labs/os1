/**
 * the resource-access cache must not turn lifecycle invalidation into a poll.
 *
 * the chat sidebar calls `resourceAccess.ensure('project', ...)` from an
 * `$effect`, once per project. the level map, the freshness set and the version
 * stamp are all reactive, so a plain read there subscribed the effect to them and
 * every `invalidate()` (ws drop, visibility change, execution gap) re-ran the
 * effect straight back into `POST .../access/resolve`, one call per project.
 */

import type { components } from '$lib/api/types'
import { flushSync } from 'svelte'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type AccessLevelResolution = components['schemas']['AccessLevelResolution']

const RESOLVE_PATH = '/v1/projects/{project_id}/access/resolve'

let resolveCalls = 0

vi.mock('$app/environment', () => ({ browser: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: null, error: null }),
		POST: vi.fn((path: string) => {
			if (path === RESOLVE_PATH) {
				resolveCalls += 1
				return Promise.resolve({ data: [resolution('editor')], error: null })
			}
			return Promise.resolve({ data: null, error: null })
		}),
		PUT: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/session.svelte', () => ({ session: { currentUserId: 'user_me' } }))

vi.mock('$lib/stores/storeEvents', () => ({
	STORE_EVENT_TYPES: {
		resourceAccessGlobal: ['access.changed'],
		resourceAccessResource: ['resource.access_changed'],
	},
	storeEventData: vi.fn(() => null),
	subscribeToStoreEvents: vi.fn(() => () => {}),
}))

const { resourceAccess } = await import('$lib/stores/resourceAccess.svelte')

function resolution(level: 'reader' | 'editor' | 'admin'): AccessLevelResolution {
	return {
		resource_type: 'project',
		resource_id: 'proj_1',
		user_id: 'user_me',
		level,
	} as AccessLevelResolution
}

/** let pending effects and the in-flight request both settle */
async function settle(): Promise<void> {
	flushSync()
	await new Promise((resolve) => setTimeout(resolve, 0))
	flushSync()
	await new Promise((resolve) => setTimeout(resolve, 0))
	flushSync()
}

describe('resourceAccess.ensure() from an effect', () => {
	beforeEach(() => {
		resolveCalls = 0
		resourceAccess.clear()
	})

	it('resolves once and does not re-resolve when the lifecycle marks it stale', async () => {
		const cleanup = $effect.root(() => {
			$effect(() => {
				void resourceAccess.ensure('project', 'proj_1', 'user_other')
			})
		})

		await settle()
		expect(resolveCalls).toBe(1)

		resourceAccess.invalidate()
		await settle()

		expect(resolveCalls).toBe(1)
		cleanup()
	})

	it('still re-resolves when a caller asks for it after invalidation', async () => {
		await resourceAccess.ensure('project', 'proj_1', 'user_other')
		expect(resolveCalls).toBe(1)

		resourceAccess.invalidate()
		await resourceAccess.ensure('project', 'proj_1', 'user_other')

		expect(resolveCalls).toBe(2)
	})

	it('serves the owner shortcut without touching the network', async () => {
		const level = await resourceAccess.ensure('project', 'proj_1', 'user_me')

		expect(level).toBe('admin')
		expect(resolveCalls).toBe(0)
	})
})
