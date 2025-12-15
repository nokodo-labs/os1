import { getContext, setContext } from 'svelte'

const SYSTEM_CHROME_KEY = Symbol('system-chrome')

export interface IslandAgentSelectorConfig {
	selectedAgent: string
	onAgentChange: (agentId: string) => void
}

export interface IslandConfig {
	agentSelector: IslandAgentSelectorConfig | null
	activityText: string | null
}

export interface SystemChromeContext {
	readonly island: IslandConfig
	readonly isDockOpen: boolean
	setIsland(config: Partial<IslandConfig>): void
	clearIsland(): void
	setAgentSelector(config: IslandAgentSelectorConfig | null): void
	setActivityText(text: string | null): void
	toggleDock(): void
	openDock(): void
	closeDock(): void
}

export function createSystemChromeContext(): SystemChromeContext {
	let agentSelector = $state<IslandAgentSelectorConfig | null>(null)
	let activityText = $state<string | null>(null)
	let isDockOpen = $state(false)

	const context: SystemChromeContext = {
		get island() {
			return {
				agentSelector,
				activityText,
			}
		},
		get isDockOpen() {
			return isDockOpen
		},
		setIsland(config) {
			if ('agentSelector' in config) agentSelector = config.agentSelector ?? null
			if ('activityText' in config) activityText = config.activityText ?? null
		},
		clearIsland() {
			agentSelector = null
			activityText = null
		},
		setAgentSelector(config) {
			agentSelector = config
		},
		setActivityText(text) {
			activityText = text
		},
		toggleDock() {
			isDockOpen = !isDockOpen
		},
		openDock() {
			isDockOpen = true
		},
		closeDock() {
			isDockOpen = false
		},
	}

	setContext(SYSTEM_CHROME_KEY, context)
	return context
}

export function useSystemChrome(): SystemChromeContext {
	const context = getContext<SystemChromeContext>(SYSTEM_CHROME_KEY)
	if (!context) {
		throw new Error('useSystemChrome must be used within a SystemChromeProvider')
	}
	return context
}
