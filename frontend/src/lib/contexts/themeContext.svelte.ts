import { onMount } from 'svelte'

type ThemeMode = 'light' | 'dark' | 'system'
type AccentColor = 'purple' | 'blue' | 'green' | 'orange' | 'pink' | 'red'

export type { AccentColor, ThemeMode }

const THEME_KEY = 'nokodo-theme-mode'
const ACCENT_KEY = 'nokodo-theme-accent'

// Default state
let mode = $state<ThemeMode>('system')
let accent = $state<AccentColor>('purple')
let resolvedMode = $state<'light' | 'dark'>('dark')

// Accent color maps for Tailwind classes
// We'll use CSS variables for more flexibility, but these helpers can be useful
export const accentColors = {
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
        primary: '#22c55e', // green-500
        secondary: '#4ade80', // green-400
        bg: 'rgba(34, 197, 94, 0.02)',
        border: 'rgba(34, 197, 94, 0.2)',
        shadow: 'rgba(34, 197, 94, 0.25)',
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
}

function updateDOM() {
    const root = document.documentElement
    const isDark =
        mode === 'dark' ||
        (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

    resolvedMode = isDark ? 'dark' : 'light'

    if (isDark) {
        root.classList.add('dark')
    } else {
        root.classList.remove('dark')
    }

    // Update CSS variables for accent color
    const colors = accentColors[accent]
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
    readonly resolvedMode: 'light' | 'dark'
    readonly accentColors: typeof accentColors
}

export function createThemeContext(): ThemeContext {
    onMount(() => {
        // Load saved preferences
        const savedMode = localStorage.getItem(THEME_KEY) as ThemeMode | null
        const savedAccent = localStorage.getItem(ACCENT_KEY) as AccentColor | null

        if (savedMode) mode = savedMode
        if (savedAccent && accentColors[savedAccent]) accent = savedAccent

        updateDOM()

        // Listen for system theme changes
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
        const handleChange = () => {
            if (mode === 'system') updateDOM()
        }
        mediaQuery.addEventListener('change', handleChange)

        return () => mediaQuery.removeEventListener('change', handleChange)
    })

    return {
        get mode() {
            return mode
        },
        setMode(newMode: ThemeMode) {
            mode = newMode
            localStorage.setItem(THEME_KEY, newMode)
            updateDOM()
        },
        get accent() {
            return accent
        },
        setAccent(newAccent: AccentColor) {
            accent = newAccent
            localStorage.setItem(ACCENT_KEY, newAccent)
            updateDOM()
        },
        get resolvedMode() {
            return resolvedMode
        },
        get accentColors() {
            return accentColors
        },
    }
}
