import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'

export type Agent = components['schemas']['Agent']

const AGENT_EVENT_TYPES = ['agent.created', 'agent.updated', 'agent.deleted']

class AgentsStore {
	list = $state<Agent[]>([])
	byId = $state<Record<string, Agent>>({})
	error = $state<string | null>(null)

	#loading = false
	#pending: string[] = []
	#unsubscribe: (() => void) | null = null

	get = (agentId: string): Agent | null => this.byId[agentId] ?? null

	load = async (): Promise<void> => {
		if (!getAccessToken()) {
			this.error = null
			this.list = []
			this.byId = {}
			return
		}
		if (this.#loading) return
		this.#loading = true
		this.error = null
		try {
			const { data, error } = await api.GET('/v1/agents')
			if (error || !data) {
				this.error = 'failed to load agents'
				return
			}
			this.list = data
			this.byId = Object.fromEntries(data.map((a) => [a.id, a]))
		} catch {
			this.error = 'failed to load agents'
		} finally {
			this.#loading = false
		}
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
		if (!AGENT_EVENT_TYPES.includes(eventType)) return

		const data = (message.data ?? message) as Record<string, unknown>
		const agentId = data.id as string | undefined
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
		if (eventType === 'agent.created') {
			if (!this.byId[agentId]) {
				this.list = [agent, ...this.list]
			}
		} else {
			this.list = this.list.map((a) => (a.id === agentId ? agent : a))
		}
		this.byId = { ...this.byId, [agentId]: agent }
	}

	init = (): void => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleEvent)
		}
	}

	cleanup = (): void => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	invalidate = (): void => {
		this.#loading = false
		this.list = []
		this.byId = {}
	}

	clear = (): void => {
		this.list = []
		this.byId = {}
		this.error = null
		this.#loading = false
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
