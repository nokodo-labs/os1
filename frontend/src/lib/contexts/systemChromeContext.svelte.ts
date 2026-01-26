import { getContext, setContext } from 'svelte'

const SYSTEM_CHROME_KEY = Symbol('system-chrome')

export interface IslandAgentSelectorConfig {
	selectedAgent: string
	onAgentChange: (agentId: string) => void
}

export type IslandActionIcon = 'plus' | 'list' | 'chevron-left'

export interface IslandAction {
	id: string
	label: string
	ariaLabel?: string
	icon: IslandActionIcon
	onClick: () => void
}

export interface IslandConfig {
	agentSelector: IslandAgentSelectorConfig | null
	activityText: string | null
	actions: IslandAction[] | null
}

/**
 * layout insets configuration.
 * used by master/detail scaffolds to reserve space in the root layout.
 */
export interface LayoutInsets {
	/** tailwind width class for the left sidebar spacer (e.g. 'w-[clamp(280px,30vw,520px)]') */
	leftWidthClass: string | null
	/** view-transition-name for the left sidebar */
	leftViewTransitionName: string | null
}

export interface SystemChromeContext {
	readonly island: IslandConfig
	readonly isDockOpen: boolean
	readonly layout: LayoutInsets
	setIsland(config: Partial<IslandConfig>): void
	clearIsland(): void
	setAgentSelector(config: IslandAgentSelectorConfig | null): void
	setActivityText(text: string | null): void
	toggleDock(): void
	openDock(): void
	closeDock(): void
	/** set layout insets (used by master/detail scaffolds) */
	setLayoutInsets(insets: Partial<LayoutInsets>): void
	/** clear layout insets */
	clearLayoutInsets(): void
}

export function createSystemChromeContext(): SystemChromeContext {
	let agentSelector = $state<IslandAgentSelectorConfig | null>(null)
	let activityText = $state<string | null>(null)
	let actions = $state<IslandAction[] | null>(null)
	let isDockOpen = $state(false)
	let leftWidthClass = $state<string | null>(null)
	let leftViewTransitionName = $state<string | null>(null)

	const context: SystemChromeContext = {
		get island() {
			return {
				agentSelector,
				activityText,
				actions,
			}
		},
		get isDockOpen() {
			return isDockOpen
		},
		get layout() {
			return {
				leftWidthClass,
				leftViewTransitionName,
			}
		},
		setIsland(config) {
			if ('agentSelector' in config) agentSelector = config.agentSelector ?? null
			if ('activityText' in config) activityText = config.activityText ?? null
			if ('actions' in config) actions = config.actions ?? null
		},
		clearIsland() {
			agentSelector = null
			activityText = null
			actions = null
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
		setLayoutInsets(insets) {
			if ('leftWidthClass' in insets) leftWidthClass = insets.leftWidthClass ?? null
			if ('leftViewTransitionName' in insets)
				leftViewTransitionName = insets.leftViewTransitionName ?? null
		},
		clearLayoutInsets() {
			leftWidthClass = null
			leftViewTransitionName = null
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
