/**
 * MCP server store - one cached list shared by the chat context panel and the
 * integrations settings section.
 *
 * cache strategy:
 * - load once per session, then serve from memory until the TTL expires or the
 *   cache is invalidated. a failed attempt also counts, so a panel that opens
 *   repeatedly never hammers an endpoint the account cannot reach.
 * - the backend emits no mcp.* stream events, so mutations patch the cached
 *   list in place instead of waiting for a push.
 * - MCP availability follows the integrations settings, so a settings change
 *   marks the cache stale (rendered data stays until the next load).
 */

import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { session } from '$lib/stores/session.svelte'
import { STORE_EVENT_TYPES, subscribeToStoreEvents } from '$lib/stores/storeEvents'

export type MCPServer = components['schemas']['MCPServer']
export type MCPServerCreate = components['schemas']['MCPServerCreate']
export type MCPServerUpdate = components['schemas']['MCPServerUpdate']
export type MCPCapabilityType = components['schemas']['MCPCapabilityType']
export type MCPDiscoveredTool = components['schemas']['MCPDiscoveredTool']
export type MCPTransport = components['schemas']['MCPTransport']

const CACHE_TTL_MS = 5 * 60 * 1000

class McpServersStore {
	list = $state<MCPServer[]>([])
	hasLoaded = $state(false)
	loading = $state(false)
	error = $state<string | null>(null)
	/** false when the account may not manage MCP servers (403/404 from the API). */
	canManage = $state(true)

	#fetchedAt = 0
	#inFlight: Promise<void> | null = null
	#unsubscribe: (() => void) | null = null

	/** servers the current user owns - the only ones they can edit or toggle. */
	readonly own = $derived.by(() => {
		const currentUserId = session.currentUserId
		return this.list.filter(
			(server) =>
				server.scope === 'user' &&
				(currentUserId === null || server.owner_user_id === currentUserId)
		)
	})

	get(serverId: string): MCPServer | null {
		return this.list.find((server) => server.id === serverId) ?? null
	}

	// lifecycle

	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = subscribeToStoreEvents(STORE_EVENT_TYPES.settings, this.invalidate)
		}
	}

	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	invalidate = (): void => {
		this.#fetchedAt = 0
	}

	clear(): void {
		this.list = []
		this.hasLoaded = false
		this.loading = false
		this.error = null
		this.canManage = true
		this.#fetchedAt = 0
	}

	// load

	async load(options?: { force?: boolean }): Promise<void> {
		const force = options?.force ?? false
		if (!getAccessToken()) return
		if (!force && this.#isFresh()) return
		if (this.#inFlight) return await this.#inFlight

		this.#inFlight = (async () => {
			this.loading = true
			try {
				const { data, error, response } = await api.GET('/v1/integrations/mcp/servers')
				if (error || !data) {
					const unavailable = response.status === 403 || response.status === 404
					this.canManage = !unavailable
					this.error = unavailable
						? 'MCP servers are not available for your account'
						: 'failed to load MCP servers'
					return
				}
				this.canManage = true
				this.error = null
				this.list = data
				this.hasLoaded = true
			} finally {
				// a failed attempt is cached too, so reopening a panel does not retry at once
				this.#fetchedAt = Date.now()
				this.loading = false
			}
		})()

		try {
			await this.#inFlight
		} finally {
			this.#inFlight = null
		}
	}

	async refresh(): Promise<void> {
		await this.load({ force: true })
	}

	// mutations

	async create(payload: MCPServerCreate): Promise<MCPServer | null> {
		const { data, error } = await api.POST('/v1/integrations/mcp/servers', { body: payload })
		if (error || !data) return null
		this.list = [data, ...this.list]
		return data
	}

	async update(serverId: string, payload: MCPServerUpdate): Promise<MCPServer | null> {
		const { data, error } = await api.PATCH('/v1/integrations/mcp/servers/{server_id}', {
			params: { path: { server_id: serverId } },
			body: payload,
		})
		if (error || !data) return null
		this.#replace(data)
		return data
	}

	async remove(serverId: string): Promise<boolean> {
		const { error } = await api.DELETE('/v1/integrations/mcp/servers/{server_id}', {
			params: { path: { server_id: serverId } },
		})
		if (error) return false
		this.list = this.list.filter((server) => server.id !== serverId)
		return true
	}

	async discover(serverId: string): Promise<MCPServer | null> {
		const { data, error } = await api.POST(
			'/v1/integrations/mcp/servers/{server_id}/discover',
			{ params: { path: { server_id: serverId } } }
		)
		if (error || !data) return null
		this.#replace(data.server)
		return data.server
	}

	async setToolEnabled(
		serverId: string,
		toolId: string,
		enabled: boolean
	): Promise<MCPServer | null> {
		const capabilityType: MCPCapabilityType = 'tool'
		const { data, error } = await api.PATCH(
			'/v1/integrations/mcp/servers/{server_id}/capabilities/{capability_type}/{capability_id}',
			{
				params: {
					path: {
						server_id: serverId,
						capability_type: capabilityType,
						capability_id: toolId,
					},
				},
				body: { enabled },
			}
		)
		if (error || !data) return null
		this.#replace(data)
		return data
	}

	// internals

	#isFresh(): boolean {
		return this.#fetchedAt !== 0 && Date.now() - this.#fetchedAt < CACHE_TTL_MS
	}

	#replace(server: MCPServer): void {
		this.list = this.list.map((item) => (item.id === server.id ? server : item))
	}
}

export const mcpServers = new McpServersStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			mcpServers.init()
		} else {
			mcpServers.cleanup()
			mcpServers.clear()
		}
	})

	if (getAccessToken()) {
		mcpServers.init()
	}
}
