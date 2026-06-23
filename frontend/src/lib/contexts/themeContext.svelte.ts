import { browser } from '$app/environment'
import { accentStore, type AccentColorKey } from '$lib/stores/accent.svelte'
import { background } from '$lib/stores/background.svelte'
import { preferences, type AccentColor, type ThemeMode } from '$lib/stores/preferences.svelte'
import { getContext, setContext } from 'svelte'

export type { AccentColor, AccentColorKey, ThemeMode }
const THEME_CONTEXT_KEY = Symbol('theme-context')

// localStorage key read by the boot script in app.html to avoid a theme flash
const RESOLVED_MODE_KEY = 'theme-resolved'

// accent color maps for Tailwind classes
// we'll use CSS variables for more flexibility, but these helpers can be useful
export const accentColors: Record<
	AccentColorKey,
	{ primary: string; rgb: string; bg: string; border: string; shadow: string }
> = {
	purple: {
		primary: '#a855f7', // purple-500
		rgb: '168 85 247',
		bg: 'rgba(168, 85, 247, 0.02)',
		border: 'rgba(168, 85, 247, 0.2)',
		shadow: 'rgba(168, 85, 247, 0.25)',
	},
	blue: {
		primary: '#3b82f6', // blue-500
		rgb: '59 130 246',
		bg: 'rgba(59, 130, 246, 0.02)',
		border: 'rgba(59, 130, 246, 0.2)',
		shadow: 'rgba(59, 130, 246, 0.25)',
	},
	green: {
		primary: '#65C466', // messages green
		rgb: '101 196 102',
		bg: 'rgba(101, 196, 102, 0.02)',
		border: 'rgba(101, 196, 102, 0.2)',
		shadow: 'rgba(101, 196, 102, 0.25)',
	},
	orange: {
		primary: '#f97316', // orange-500
		rgb: '249 115 22',
		bg: 'rgba(249, 115, 22, 0.02)',
		border: 'rgba(249, 115, 22, 0.2)',
		shadow: 'rgba(249, 115, 22, 0.25)',
	},
	pink: {
		primary: '#ec4899', // pink-500
		rgb: '236 72 153',
		bg: 'rgba(236, 72, 153, 0.02)',
		border: 'rgba(236, 72, 153, 0.2)',
		shadow: 'rgba(236, 72, 153, 0.25)',
	},
	red: {
		primary: '#ef4444', // red-500
		rgb: '239 68 68',
		bg: 'rgba(239, 68, 68, 0.02)',
		border: 'rgba(239, 68, 68, 0.2)',
		shadow: 'rgba(239, 68, 68, 0.25)',
	},
	yellow: {
		primary: '#fde68a', // library folder yellow
		rgb: '253 230 138',
		bg: 'rgba(253, 230, 138, 0.02)',
		border: 'rgba(253, 230, 138, 0.2)',
		shadow: 'rgba(253, 230, 138, 0.25)',
	},
	gray: {
		primary: '#6b7280', // gray-500
		rgb: '107 114 128',
		bg: 'rgba(107, 114, 128, 0.02)',
		border: 'rgba(107, 114, 128, 0.2)',
		shadow: 'rgba(107, 114, 128, 0.25)',
	},
	notes: {
		primary: '#fbbc04', // notes app yellow
		rgb: '251 188 4',
		bg: 'rgba(251, 188, 4, 0.02)',
		border: 'rgba(251, 188, 4, 0.2)',
		shadow: 'rgba(251, 188, 4, 0.25)',
	},
	reminders: {
		primary: '#4285f4', // reminders app blue
		rgb: '66 133 244',
		bg: 'rgba(66, 133, 244, 0.02)',
		border: 'rgba(66, 133, 244, 0.2)',
		shadow: 'rgba(66, 133, 244, 0.25)',
	},
	calendar: {
		primary: '#d45446', // paper calendar red
		rgb: '212 84 70',
		bg: 'rgba(212, 84, 70, 0.02)',
		border: 'rgba(212, 84, 70, 0.2)',
		shadow: 'rgba(212, 84, 70, 0.24)',
	},
	lilac: {
		primary: '#c4b5fd', // lilac (violet-300)
		rgb: '196 181 253',
		bg: 'rgba(196, 181, 253, 0.02)',
		border: 'rgba(196, 181, 253, 0.2)',
		shadow: 'rgba(196, 181, 253, 0.25)',
	},
	petrol: {
		primary: '#0f766e',
		rgb: '15 118 110',
		bg: 'rgba(15, 118, 110, 0.03)',
		border: 'rgba(15, 118, 110, 0.24)',
		shadow: 'rgba(15, 118, 110, 0.28)',
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
	root.style.setProperty('--accent-rgb', colors.rgb)
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
	const mode = $derived(preferences.data.appearance.themeMode ?? 'auto')
	const accent = $derived(preferences.data.appearance.accent ?? 'purple')
	const autoAccentColors = $derived(preferences.data.appearance.autoAccentColors ?? true)

	// resolved accent: if autoAccentColors is on, use accent store; otherwise use user preference
	const resolvedAccent = $derived.by((): AccentColorKey => {
		if (autoAccentColors) {
			return accentStore.current
		}
		return accent
	})

	// auto mode matches the theme to the active background's luminance
	const resolvedMode = $derived.by((): 'light' | 'dark' => {
		if (mode === 'dark') return 'dark'
		if (mode === 'light') return 'light'
		return background.resolvedLuminance === 'dark' ? 'dark' : 'light'
	})

	$effect(() => {
		if (!browser) return
		updateDOM(resolvedMode, resolvedAccent)
		try {
			localStorage.setItem(RESOLVED_MODE_KEY, resolvedMode)
		} catch {
			// ignore storage failures
		}
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
