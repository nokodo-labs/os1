import { browser } from '$app/environment'

const STORAGE_KEY = 'selected-agent-id'

function readStoredSelectedAgentId(): string {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY)
		return typeof raw === 'string' ? raw : ''
	} catch {
		return ''
	}
}

export let selectedAgentId = $state<string>(readStoredSelectedAgentId())

$effect(() => {
	if (!browser) return
	try {
		if (selectedAgentId) window.localStorage.setItem(STORAGE_KEY, selectedAgentId)
		else window.localStorage.removeItem(STORAGE_KEY)
	} catch {
		void 0
	}
})

export function setSelectedAgentId(agentId: string): void {
	selectedAgentId = agentId
}

export function getSelectedAgentId(): string {
	return selectedAgentId
}
