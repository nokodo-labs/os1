import type { components } from '$lib/api/types'
import { v1Client } from '$lib/api/v1/client'

export type Agent = components['schemas']['Agent']

export let agentsList = $state<Agent[]>([])
export let agentsById = $state<Record<string, Agent>>({})

let isLoadingAgents = false
const pendingAgentIds: string[] = []

export function getAgentFromCache(agentId: string): Agent | null {
	const byId = agentsById
	return byId[agentId] ?? null
}

export async function loadAgents(): Promise<void> {
	if (isLoadingAgents) return
	isLoadingAgents = true
	try {
		const { data, error } = await v1Client().GET('/agents')
		if (error || !data) return

		agentsList = data
		agentsById = Object.fromEntries(data.map((a) => [a.id, a]))
	} finally {
		isLoadingAgents = false
	}
}

export async function ensureAgent(agentId: string): Promise<Agent | null> {
	if (!agentId) return null
	const existing = getAgentFromCache(agentId)
	if (existing) return existing
	if (pendingAgentIds.includes(agentId)) return null

	pendingAgentIds.push(agentId)
	try {
		const { data, error } = await v1Client().GET('/agents/{agent_id}', {
			params: { path: { agent_id: agentId } },
		})
		if (error || !data) return null

		agentsById = { ...agentsById, [agentId]: data }
		return data
	} finally {
		const idx = pendingAgentIds.indexOf(agentId)
		if (idx >= 0) pendingAgentIds.splice(idx, 1)
	}
}

export async function ensureAgents(agentIds: string[]): Promise<void> {
	const seen: Record<string, true> = {}
	const unique: string[] = []
	for (const id of agentIds) {
		if (!id) continue
		if (seen[id]) continue
		seen[id] = true
		unique.push(id)
	}
	await Promise.all(unique.map((id) => ensureAgent(id)))
}
