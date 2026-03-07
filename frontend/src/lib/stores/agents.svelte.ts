import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'

export type Agent = components['schemas']['Agent']

class AgentsStore {
	list = $state<Agent[]>([])
	byId = $state<Record<string, Agent>>({})
	error = $state<string | null>(null)

	#loading = false
	#pending: string[] = []

	get = (agentId: string): Agent | null => this.byId[agentId] ?? null

	load = async (): Promise<void> => {
		if (this.#loading) return
		this.#loading = true
		this.error = null
		try {
			const { data, error } = await apiClient().GET('/v1/agents')
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
		const existing = this.get(agentId)
		if (existing) return existing
		if (this.#pending.includes(agentId)) return null

		this.#pending.push(agentId)
		try {
			const { data, error } = await apiClient().GET('/v1/agents/{agent_id}', {
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
}

export const agents = new AgentsStore()
