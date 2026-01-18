import { browser } from '$app/environment'

const STORAGE_KEY = 'selected-agent-id'

function readStored(): string {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY)
		return typeof raw === 'string' ? raw : ''
	} catch {
		return ''
	}
}

class SelectedAgentStore {
	id = $state<string>(readStored())

	set = (agentId: string) => {
		this.id = agentId
		if (!browser) return
		try {
			if (agentId) window.localStorage.setItem(STORAGE_KEY, agentId)
			else window.localStorage.removeItem(STORAGE_KEY)
		} catch {
			// ignore
		}
	}

	clear = () => this.set('')
}

export const selectedAgent = new SelectedAgentStore()
