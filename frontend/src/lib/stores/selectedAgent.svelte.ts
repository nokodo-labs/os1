import { browser } from '$app/environment'
import { settingsState } from '$lib/stores/settings.svelte'

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

	/** the admin-configured default agent id, or empty string */
	get defaultId(): string {
		return settingsState.data?.ai?.default_agent_id ?? ''
	}

	/**
	 * resolve the best agent id from a list.
	 * priority: current stored id → admin default → first in list.
	 * returns the resolved id, or empty string if the list is empty.
	 */
	resolveDefault(agentList: { id: string }[]): string {
		if (agentList.length === 0) return ''
		// already valid
		if (this.id && agentList.some((a) => a.id === this.id)) return this.id
		// admin default
		const def = this.defaultId
		if (def && agentList.some((a) => a.id === def)) return def
		// first in list
		return agentList[0].id
	}

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
