/**
 * tests for the MCP server cache: load-once semantics, cache hits, staleness
 * from invalidation, and the wipe on logout.
 */

import type { components } from '$lib/api/types'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type MCPServer = components['schemas']['MCPServer']

const listResponses: { data?: MCPServer[]; error?: unknown; response: { status: number } }[] = []
const patchResponses: { data?: MCPServer; error?: unknown }[] = []
let listCalls = 0
let settingsHandler: (() => void) | null = null

vi.mock('$app/environment', () => ({ browser: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn((path: string) => {
			if (path === '/v1/integrations/mcp/servers') {
				listCalls += 1
				return Promise.resolve(
					listResponses.shift() ?? { data: [], error: null, response: { status: 200 } }
				)
			}
			return Promise.resolve({ data: null, error: null, response: { status: 200 } })
		}),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn(() => Promise.resolve(patchResponses.shift() ?? { data: null, error: null })),
		DELETE: vi.fn().mockResolvedValue({ error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: { currentUserId: 'user_me' },
}))

vi.mock('$lib/stores/storeEvents', () => ({
	STORE_EVENT_TYPES: { settings: ['settings.updated'] },
	subscribeToStoreEvents: vi.fn((_types: readonly string[], handler: () => void) => {
		settingsHandler = handler
		return () => {
			settingsHandler = null
		}
	}),
}))

const { mcpServers } = await import('$lib/stores/mcpServers.svelte')

function makeServer(id: string, name: string, ownerId: string | null = 'user_me'): MCPServer {
	return {
		id,
		name,
		scope: ownerId === null ? 'global' : 'user',
		owner_user_id: ownerId,
		transport: 'streamable_http',
		auth_type: 'none',
		enabled: true,
		status: 'ready',
		has_credentials: false,
		discovered_tools: [],
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
	}
}

function queueList(servers: MCPServer[], status = 200): void {
	listResponses.push({ data: servers, error: null, response: { status } })
}

function queueFailure(status: number): void {
	listResponses.push({ error: { detail: 'nope' }, response: { status } })
}

describe('mcpServers store', () => {
	beforeEach(() => {
		mcpServers.cleanup()
		mcpServers.clear()
		listResponses.length = 0
		patchResponses.length = 0
		listCalls = 0
	})

	it('loads once and serves later reads from the cache', async () => {
		queueList([makeServer('mcp_1', 'first')])

		await mcpServers.load()
		await mcpServers.load()
		await mcpServers.load()

		expect(listCalls).toBe(1)
		expect(mcpServers.hasLoaded).toBe(true)
		expect(mcpServers.own.map((server) => server.name)).toEqual(['first'])
	})

	it('shares one request between concurrent callers', async () => {
		queueList([makeServer('mcp_1', 'first')])

		await Promise.all([mcpServers.load(), mcpServers.load()])

		expect(listCalls).toBe(1)
	})

	it('keeps a failed attempt cached so a reopened panel does not retry at once', async () => {
		queueFailure(403)

		await mcpServers.load()
		await mcpServers.load()

		expect(listCalls).toBe(1)
		expect(mcpServers.canManage).toBe(false)
		expect(mcpServers.hasLoaded).toBe(false)
		expect(mcpServers.error).toBe('MCP servers are not available for your account')
	})

	it('only exposes servers the current user owns', async () => {
		queueList([
			makeServer('mcp_1', 'mine'),
			makeServer('mcp_2', 'someone else', 'user_other'),
			makeServer('mcp_3', 'admin managed', null),
		])

		await mcpServers.load()

		expect(mcpServers.own.map((server) => server.id)).toEqual(['mcp_1'])
		expect(mcpServers.list).toHaveLength(3)
	})

	it('refetches after invalidate while keeping rendered data', async () => {
		queueList([makeServer('mcp_1', 'first')])
		queueList([makeServer('mcp_1', 'renamed')])

		await mcpServers.load()
		mcpServers.invalidate()

		expect(mcpServers.own.map((server) => server.name)).toEqual(['first'])

		await mcpServers.load()

		expect(listCalls).toBe(2)
		expect(mcpServers.own.map((server) => server.name)).toEqual(['renamed'])
	})

	it('marks the cache stale when settings change', async () => {
		queueList([makeServer('mcp_1', 'first')])
		queueList([makeServer('mcp_1', 'first')])

		mcpServers.init()
		await mcpServers.load()
		expect(listCalls).toBe(1)

		settingsHandler?.()
		await mcpServers.load()

		expect(listCalls).toBe(2)
	})

	it('wipes everything on clear and reloads afterwards', async () => {
		queueList([makeServer('mcp_1', 'first')])
		queueList([makeServer('mcp_2', 'after logout')])

		await mcpServers.load()
		mcpServers.clear()

		expect(mcpServers.list).toEqual([])
		expect(mcpServers.hasLoaded).toBe(false)
		expect(mcpServers.error).toBeNull()

		await mcpServers.load()

		expect(listCalls).toBe(2)
		expect(mcpServers.own.map((server) => server.id)).toEqual(['mcp_2'])
	})

	it('patches the cached list on mutations instead of refetching', async () => {
		queueList([makeServer('mcp_1', 'first'), makeServer('mcp_2', 'second')])
		await mcpServers.load()

		patchResponses.push({ data: { ...makeServer('mcp_1', 'renamed'), enabled: false } })
		await mcpServers.update('mcp_1', { name: 'renamed' })

		expect(listCalls).toBe(1)
		expect(mcpServers.get('mcp_1')?.name).toBe('renamed')

		await mcpServers.remove('mcp_2')

		expect(mcpServers.own.map((server) => server.id)).toEqual(['mcp_1'])
		expect(listCalls).toBe(1)
	})
})
