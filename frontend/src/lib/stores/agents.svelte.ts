import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import {
	STORE_EVENT_TYPES,
	storeEventPayload,
	storeEventString,
	subscribeToStoreEvents,
} from '$lib/stores/storeEvents'

export type Agent = components['schemas']['Agent']

const CACHE_TTL_MS = 5 * 60 * 1000

class AgentsStore {
	list = $state<Agent[]>([])
	byId = $state<Record<string, Agent>>({})
	error = $state<string | null>(null)

	#hasLoaded = $state(false)
	// plain fields on purpose: an $effect calling load() must not subscribe to the
	// freshness stamp, or every invalidation would re-run it into /v1/agents.
	#fetchedAt = 0
	#inFlight: Promise<void> | null = null
	#pending: string[] = []
	#unsubscribe: (() => void) | null = null

	get hasLoaded(): boolean {
		return this.#hasLoaded
	}

	get = (agentId: string): Agent | null => this.byId[agentId] ?? null

	load = async (options?: { force?: boolean }): Promise<void> => {
		if (!getAccessToken()) {
			this.error = null
			this.list = []
			this.byId = {}
			this.#hasLoaded = false
			this.#fetchedAt = 0
			return
		}
		const force = options?.force ?? false
		if (!force && this.#isFresh()) return
		if (this.#inFlight) return await this.#inFlight

		this.#inFlight = (async () => {
			this.error = null
			try {
				const { data, error } = await api.GET('/v1/agents')
				if (error || !data) {
					if (this.list.length === 0) {
						this.error = 'failed to load agents'
					}
					return
				}
				this.list = data
				this.byId = Object.fromEntries(data.map((a) => [a.id, a]))
				this.#hasLoaded = true
			} catch {
				if (this.list.length === 0) {
					this.error = 'failed to load agents'
				}
			} finally {
				// a failed attempt is stamped too, so a remount does not retry at once
				this.#fetchedAt = Date.now()
			}
		})()

		try {
			await this.#inFlight
		} finally {
			this.#inFlight = null
		}
	}

	#isFresh(): boolean {
		return this.#fetchedAt !== 0 && Date.now() - this.#fetchedAt < CACHE_TTL_MS
	}

	ensure = async (agentId: string): Promise<Agent | null> => {
		if (!agentId) return null
		if (!getAccessToken()) return null
		const existing = this.get(agentId)
		if (existing) return existing
		if (this.#pending.includes(agentId)) return null

		this.#pending.push(agentId)
		try {
			const { data, error } = await api.GET('/v1/agents/{agent_id}', {
				params: { path: { agent_id: agentId } },
			})
			if (error || !data) return null
			this.byId = { ...this.byId, [agentId]: data }
			return data
		} finally {
			const idx = this.#pending.indexOf(agentId)
			if (idx >= 0) this.#pending.splice(idx, 1)
		}
	}

	ensureMany = async (agentIds: string[]): Promise<void> => {
		const seen: Record<string, true> = {}
		const unique: string[] = []
		for (const id of agentIds) {
			if (!id || seen[id]) continue
			seen[id] = true
			unique.push(id)
		}
		await Promise.all(unique.map((id) => this.ensure(id)))
	}

	#handleEvent = (message: StreamMessage): void => {
		const eventType = message.type
		const data = storeEventPayload(message)
		const agentId = storeEventString(message, ['id'])
		if (!agentId) return

		if (eventType === 'agent.deleted') {
			this.list = this.list.filter((a) => a.id !== agentId)
			const updated = { ...this.byId }
			delete updated[agentId]
			this.byId = updated
			return
		}

		// agent.created or agent.updated - data contains full agent payload
		const agent = data as unknown as Agent
		if (!this.byId[agentId]) {
			// new agent (created, or user just gained access via updated rules)
			this.list = [agent, ...this.list]
		} else {
			this.list = this.list.map((a) => (a.id === agentId ? agent : a))
		}
		this.byId = { ...this.byId, [agentId]: agent }
	}

	init = (): void => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = subscribeToStoreEvents(STORE_EVENT_TYPES.agents, this.#handleEvent)
		}
	}

	cleanup = (): void => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	invalidate = (): void => {
		this.#fetchedAt = 0
		// purposefully do not clear list and byId to avoid showing empty state / error
		// will fetch fresh data on next load
	}

	refresh = async (): Promise<void> => {
		await this.load({ force: true })
	}

	clear = (): void => {
		this.list = []
		this.byId = {}
		this.error = null
		this.#fetchedAt = 0
		this.#inFlight = null
		this.#hasLoaded = false
	}
}

export const agents = new AgentsStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			agents.init()
		} else {
			agents.cleanup()
			agents.clear()
		}
	})
}
