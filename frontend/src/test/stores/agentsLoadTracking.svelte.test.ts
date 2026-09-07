/**
 * the agents store must not refetch `/v1/agents` on every mount.
 *
 * `agents.load()` had no freshness check at all, so each chat page (and each
 * agent selector) that called it from an `$effect` on mount hit the endpoint
 * again. it now follows the same contract as `projects` / `mcpServers`: a ttl
 * short-circuit, in-flight dedupe, and invalidation that only marks stale.
 */

import type { components } from '$lib/api/types'
import { flushSync } from 'svelte'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Agent = components['schemas']['Agent']

let listCalls = 0

vi.mock('$app/environment', () => ({ browser: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn((path: string) => {
			if (path === '/v1/agents') {
				listCalls += 1
				return Promise.resolve({ data: [makeAgent('agent_1')], error: null })
			}
			return Promise.resolve({ data: null, error: null })
		}),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/storeEvents', () => ({
	STORE_EVENT_TYPES: { agents: ['agent.created', 'agent.updated', 'agent.deleted'] },
	storeEventPayload: vi.fn(() => null),
	storeEventString: vi.fn(() => null),
	subscribeToStoreEvents: vi.fn(() => () => {}),
}))

const { agents } = await import('$lib/stores/agents.svelte')

function makeAgent(id: string): Agent {
	return {
		id,
		name: id,
		description: '',
		owner_id: 'user_me',
		created_at: '2026-08-29T00:00:00Z',
		updated_at: '2026-08-29T00:00:00Z',
	} as Agent
}

/** let pending effects and the in-flight request both settle */
async function settle(): Promise<void> {
	flushSync()
	await new Promise((resolve) => setTimeout(resolve, 0))
	flushSync()
	await new Promise((resolve) => setTimeout(resolve, 0))
	flushSync()
}

function mountLoadEffect(): () => void {
	return $effect.root(() => {
		$effect(() => {
			void agents.load()
		})
	})
}

describe('agents.load() freshness', () => {
	beforeEach(() => {
		listCalls = 0
		agents.clear()
	})

	afterEach(() => {
		vi.restoreAllMocks()
	})

	it('does not refetch on a remount inside the ttl', async () => {
		const first = mountLoadEffect()
		await settle()
		expect(listCalls).toBe(1)
		first()

		const second = mountLoadEffect()
		await settle()
		expect(listCalls).toBe(1)
		second()
	})

	it('dedupes concurrent callers into one request', async () => {
		await Promise.all([agents.load(), agents.load(), agents.load()])

		expect(listCalls).toBe(1)
		expect(agents.hasLoaded).toBe(true)
	})

	it('does not refetch from an effect when the lifecycle marks it stale', async () => {
		const cleanup = mountLoadEffect()
		await settle()
		expect(listCalls).toBe(1)

		agents.invalidate()
		await settle()

		expect(listCalls).toBe(1)
		cleanup()
	})

	it('refetches when a caller asks for it after invalidation', async () => {
		await agents.load()
		expect(listCalls).toBe(1)

		agents.invalidate()
		await agents.load()

		expect(listCalls).toBe(2)
	})

	it('refetches once the ttl has expired', async () => {
		await agents.load()
		expect(listCalls).toBe(1)

		const start = Date.now()
		vi.spyOn(Date, 'now').mockReturnValue(start + 6 * 60 * 1000)
		await agents.load()

		expect(listCalls).toBe(2)
	})

	it('clears the freshness stamp on logout', async () => {
		await agents.load()
		expect(listCalls).toBe(1)

		agents.clear()
		expect(agents.hasLoaded).toBe(false)
		await agents.load()

		expect(listCalls).toBe(2)
	})
})
