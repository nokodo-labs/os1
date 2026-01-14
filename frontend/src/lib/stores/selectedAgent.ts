import { get, writable } from 'svelte/store'

const STORAGE_KEY = 'selected-agent-id'

/** persisted agent selection used across routes. */

function readStoredSelectedAgentId(): string {
	if (typeof window === 'undefined') return ''
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY)
		return typeof raw === 'string' ? raw : ''
	} catch {
		return ''
	}
}

export const selectedAgentId = writable<string>(readStoredSelectedAgentId())

if (typeof window !== 'undefined') {
	selectedAgentId.subscribe((value) => {
		try {
			if (value) window.localStorage.setItem(STORAGE_KEY, value)
			else window.localStorage.removeItem(STORAGE_KEY)
		} catch {
			void 0
		}
	})
}

export function setSelectedAgentId(agentId: string): void {
	selectedAgentId.set(agentId)
}

export function getSelectedAgentId(): string {
	return get(selectedAgentId)
}
