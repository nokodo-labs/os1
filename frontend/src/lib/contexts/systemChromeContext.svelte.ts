import type { Snippet } from 'svelte'
import { getContext, setContext } from 'svelte'

const SYSTEM_CHROME_KEY = Symbol('system-chrome')

export interface IslandConfig {
	/** context-specific action controls for the left section (pages inject their components here) */
	contextActions: Snippet | null
	/** pulse area content for the center section (future: rich activity indicators) */
	pulse: string | null
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
	/**
	 * whether the chat shell - the AI-chat sidebar, its rail and its swipe - is
	 * part of this view.
	 *
	 * the route alone cannot answer this: a conversation and an AI chat share the
	 * `/c/` route, but a conversation is a different viewing mode that the chat
	 * sidebar does not list and cannot navigate.
	 */
	readonly hasChatShell: boolean
	setIsland(config: Partial<IslandConfig>): void
	clearIsland(): void
	setContextActions(contextActions: Snippet | null): void
	setPulse(text: string | null): void
	toggleDock(): void
	openDock(): void
	closeDock(): void
	/** set layout insets (used by master/detail scaffolds) */
	setLayoutInsets(insets: Partial<LayoutInsets>): void
	/** clear layout insets */
	clearLayoutInsets(): void
	/** opt the current view out of (or back into) the chat shell. */
	setChatShell(enabled: boolean): void
}

export function createSystemChromeContext(): SystemChromeContext {
	let contextActions = $state<Snippet | null>(null)
	let pulse = $state<string | null>(null)
	let isDockOpen = $state(false)
	let leftWidthClass = $state<string | null>(null)
	let leftViewTransitionName = $state<string | null>(null)
	// present by default: only a view that knows it is not an AI chat opts out
	let hasChatShell = $state(true)

	const context: SystemChromeContext = {
		get island() {
			return {
				contextActions,
				pulse,
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
		get hasChatShell() {
			return hasChatShell
		},
		setIsland(config) {
			if ('contextActions' in config) contextActions = config.contextActions ?? null
			if ('pulse' in config) pulse = config.pulse ?? null
		},
		clearIsland() {
			contextActions = null
			pulse = null
		},
		setContextActions(ctx) {
			contextActions = ctx
		},
		setPulse(text) {
			pulse = text
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
		setChatShell(enabled) {
			hasChatShell = enabled
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
