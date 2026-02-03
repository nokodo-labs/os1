import { browser } from '$app/environment'
import { accentStore, type AccentColorKey } from '$lib/stores/accent.svelte'
import { preferences, type AccentColor, type ThemeMode } from '$lib/stores/preferences.svelte'
import { getContext, onMount, setContext } from 'svelte'

export type { AccentColor, AccentColorKey, ThemeMode }
const THEME_CONTEXT_KEY = Symbol('theme-context')

let prefersDark = $state(false)

// accent color maps for Tailwind classes
// we'll use CSS variables for more flexibility, but these helpers can be useful
export const accentColors: Record<
	AccentColorKey,
	{ primary: string; secondary: string; bg: string; border: string; shadow: string }
> = {
	purple: {
		primary: '#a855f7', // purple-500
		secondary: '#c084fc', // purple-400
		bg: 'rgba(168, 85, 247, 0.02)',
		border: 'rgba(168, 85, 247, 0.2)',
		shadow: 'rgba(168, 85, 247, 0.25)',
	},
	blue: {
		primary: '#3b82f6', // blue-500
		secondary: '#60a5fa', // blue-400
		bg: 'rgba(59, 130, 246, 0.02)',
		border: 'rgba(59, 130, 246, 0.2)',
		shadow: 'rgba(59, 130, 246, 0.25)',
	},
	green: {
		primary: '#34c759', // imessage green
		secondary: '#4ade80', // green-400
		bg: 'rgba(52, 199, 89, 0.02)',
		border: 'rgba(52, 199, 89, 0.2)',
		shadow: 'rgba(52, 199, 89, 0.25)',
	},
	orange: {
		primary: '#f97316', // orange-500
		secondary: '#fb923c', // orange-400
		bg: 'rgba(249, 115, 22, 0.02)',
		border: 'rgba(249, 115, 22, 0.2)',
		shadow: 'rgba(249, 115, 22, 0.25)',
	},
	pink: {
		primary: '#ec4899', // pink-500
		secondary: '#f472b6', // pink-400
		bg: 'rgba(236, 72, 153, 0.02)',
		border: 'rgba(236, 72, 153, 0.2)',
		shadow: 'rgba(236, 72, 153, 0.25)',
	},
	red: {
		primary: '#ef4444', // red-500
		secondary: '#f87171', // red-400
		bg: 'rgba(239, 68, 68, 0.02)',
		border: 'rgba(239, 68, 68, 0.2)',
		shadow: 'rgba(239, 68, 68, 0.25)',
	},
	yellow: {
		primary: '#fbbc04', // google keep yellow
		secondary: '#fde68a', // windows folder yellow (light)
		bg: 'rgba(251, 188, 4, 0.02)',
		border: 'rgba(251, 188, 4, 0.2)',
		shadow: 'rgba(251, 188, 4, 0.25)',
	},
	gray: {
		primary: '#6b7280', // gray-500
		secondary: '#9ca3af', // gray-400
		bg: 'rgba(107, 114, 128, 0.02)',
		border: 'rgba(107, 114, 128, 0.2)',
		shadow: 'rgba(107, 114, 128, 0.25)',
	},
}

// selectable accent colors (user-choosable in settings, matches API schema)
export const selectableAccentColors: AccentColor[] = [
	'purple',
	'blue',
	'green',
	'orange',
	'pink',
	'red',
]

function updateDOM(nextResolvedMode: 'light' | 'dark', nextAccent: AccentColorKey) {
	const root = document.documentElement
	const isDark = nextResolvedMode === 'dark'

	if (isDark) {
		root.classList.add('dark')
	} else {
		root.classList.remove('dark')
	}

	// update CSS variables for accent color
	const colors = accentColors[nextAccent]
	root.style.setProperty('--accent-primary', colors.primary)
	root.style.setProperty('--accent-secondary', colors.secondary)
	root.style.setProperty('--accent-bg', colors.bg)
	root.style.setProperty('--accent-border', colors.border)
	root.style.setProperty('--accent-shadow', colors.shadow)
}

interface ThemeContext {
	readonly mode: ThemeMode
	setMode(newMode: ThemeMode): void
	readonly accent: AccentColor
	setAccent(newAccent: AccentColor): void
	readonly autoAccentColors: boolean
	setAutoAccentColors(enabled: boolean): void
	readonly resolvedAccent: AccentColorKey
	readonly resolvedMode: 'light' | 'dark'
	readonly accentColors: typeof accentColors
}

export function createThemeContext(): ThemeContext {
	// keep preferences hydrated based on session state (tracked reactively)
	$effect(() => {
		return preferences.startSync()
	})

	const mode = $derived(preferences.data.appearance.themeMode ?? 'system')
	const accent = $derived(preferences.data.appearance.accent ?? 'purple')
	const autoAccentColors = $derived(preferences.data.appearance.autoAccentColors ?? true)

	// resolved accent: if autoAccentColors is on, use accent store; otherwise use user preference
	const resolvedAccent = $derived.by((): AccentColorKey => {
		if (autoAccentColors) {
			return accentStore.current
		}
		return accent
	})

	const resolvedMode = $derived.by((): 'light' | 'dark' => {
		if (mode === 'dark') return 'dark'
		if (mode === 'light') return 'light'
		return prefersDark ? 'dark' : 'light'
	})

	onMount(() => {
		if (!browser) return

		// listen for system theme changes
		const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
		prefersDark = mediaQuery.matches
		const handleChange = () => (prefersDark = mediaQuery.matches)
		mediaQuery.addEventListener('change', handleChange)
		return () => mediaQuery.removeEventListener('change', handleChange)
	})

	$effect(() => {
		if (!browser) return
		updateDOM(resolvedMode, resolvedAccent)
	})

	return {
		get mode() {
			return mode
		},
		setMode(newMode: ThemeMode) {
			void preferences.update('appearance', { themeMode: newMode })
		},
		get accent() {
			return accent
		},
		setAccent(newAccent: AccentColor) {
			void preferences.update('appearance', { accent: newAccent })
		},
		get autoAccentColors() {
			return autoAccentColors
		},
		setAutoAccentColors(enabled: boolean) {
			void preferences.update('appearance', { autoAccentColors: enabled })
		},
		get resolvedAccent() {
			return resolvedAccent
		},
		get resolvedMode() {
			return resolvedMode
		},
		get accentColors() {
			return accentColors
		},
	}
}

/**
 * set the theme context. Call this in the root layout after creating the context.
 */
export function setThemeContext(ctx: ThemeContext): void {
	setContext(THEME_CONTEXT_KEY, ctx)
}

/**
 * get the theme context from a child component.
 */
export function useTheme(): ThemeContext {
	const ctx = getContext<ThemeContext | undefined>(THEME_CONTEXT_KEY)
	if (!ctx) {
		throw new Error('useTheme must be used within a component tree that has setThemeContext')
	}
	return ctx
}
