/**
 * background store - centralized resolver
 *
 * single source of truth for the active background and static color.
 * resolves the final background based on (in priority order):
 *
 *   1. page-level override -> any page can call `background.setPage(bg)`
 *   2. auto mode + device GPU tier:
 *        high  -> darkveil
 *        mid   -> lightrays
 *        low   -> static (uses resolved static color)
 *   3. manual mode -> user preference `appearance.background`
 *
 * auth pages should use `background.setPage` / `background.clearPage`
 * inside an `$effect` with an if/else pattern (no cleanup return) to
 * avoid race conditions with the BackgroundManager transition guard.
 */

import type {
	BackgroundConfig,
	BackgroundType,
} from '$lib/components/backgrounds/BackgroundManager.svelte'
import {
	BACKGROUND_LUMINANCE,
	colorLuminance,
	type BackgroundLuminance,
} from '$lib/components/backgrounds/backgroundDefaults'
import { device } from '$lib/stores/device.svelte'
import { preferences } from '$lib/stores/preferences.svelte'
import { settingsState } from '$lib/stores/settings.svelte'
import { debounce } from '$lib/utils'

// constants

export const DEFAULT_STATIC_COLOR = '#171717'

const DEFAULT_BACKGROUND: BackgroundType = 'lightrays'

/** map GPU tier -> default background for auto mode */
const TIER_BACKGROUNDS: Record<string, BackgroundType> = {
	high: 'darkveil',
	mid: 'lightrays',
	low: 'static',
}

// internal reactive state

let pageOverride = $state<BackgroundType | null>(null)
let pageConfigOverride = $state<BackgroundConfig | null>(null)
// instant local static color while the picker is dragged; API persist is debounced
let staticColorDraft = $state<string | null>(null)

// private derived

const _auth = $derived.by(
	(): BackgroundType =>
		(settingsState.data?.ui?.auth_pages_background as BackgroundType) ?? DEFAULT_BACKGROUND
)

const _resolved = $derived.by((): BackgroundType => {
	if (pageOverride !== null) return pageOverride

	const isAuto = preferences.data.appearance.autoBackground ?? true
	if (isAuto) return TIER_BACKGROUNDS[device.gpuTier] ?? DEFAULT_BACKGROUND

	return preferences.data.appearance.background ?? DEFAULT_BACKGROUND
})

const _resolvedStaticColor = $derived(
	staticColorDraft ?? preferences.data.appearance.staticColor ?? DEFAULT_STATIC_COLOR
)

// perceived luminance of the active background; static uses its resolved color
const _resolvedLuminance = $derived.by((): BackgroundLuminance => {
	if (_resolved === 'static') return colorLuminance(_resolvedStaticColor)
	return BACKGROUND_LUMINANCE[_resolved]
})

const _autoBackground = $derived(preferences.data.appearance.autoBackground ?? true)
const _userBackground = $derived(preferences.data.appearance.background ?? DEFAULT_BACKGROUND)
const _userStaticColor = $derived(
	staticColorDraft ?? preferences.data.appearance.staticColor ?? DEFAULT_STATIC_COLOR
)

// trailing-debounced API persist; clears the local draft once preferences sync
const persistStaticColor = debounce((color: string) => {
	void preferences.updateWallpaper({ staticColor: color }).then(() => {
		staticColorDraft = null
	})
}, 250)

// public API

export const background = {
	// resolved (read by layout / BackgroundManager)

	/** final resolved background after all resolution layers */
	get resolved() {
		return _resolved
	},

	/** final resolved static color */
	get resolvedStaticColor() {
		return _resolvedStaticColor
	},

	/** perceived luminance ('dark' | 'light') of the active background */
	get resolvedLuminance() {
		return _resolvedLuminance
	},

	/** auth background from admin settings - use with `setPage` in auth pages */
	get auth() {
		return _auth
	},

	/** optional page-level config override for BackgroundManager */
	get pageConfig() {
		return pageConfigOverride
	},

	// preference reads (for settings UI)

	get autoBackground() {
		return _autoBackground
	},

	get userBackground() {
		return _userBackground
	},

	get userStaticColor() {
		return _userStaticColor
	},

	// preference writes

	setAutoBackground(enabled: boolean) {
		void preferences.updateWallpaper({ autoBackground: enabled })
	},

	setBackground(bg: BackgroundType) {
		void preferences.updateWallpaper({ background: bg })
	},

	setStaticColor(color: string) {
		// update the resolved color instantly for live theme/background feedback,
		// debounce the API write since the color picker spams updates while dragging
		staticColorDraft = color
		persistStaticColor(color)
	},

	// page override

	/**
	 * set a per-page background override.
	 * use inside `$effect` with if/else (not cleanup return):
	 * ```
	 * $effect(() => {
	 *   if (condition) background.setPage(bg)
	 *   else background.clearPage()
	 * })
	 * ```
	 */
	setPage(bg: BackgroundType) {
		pageOverride = bg
	},

	/** clear the per-page override */
	clearPage() {
		pageOverride = null
	},

	/** set a per-page background config override */
	setPageConfig(config: BackgroundConfig) {
		pageConfigOverride = { ...config }
	},

	/** clear the per-page background config override */
	clearPageConfig() {
		pageConfigOverride = null
	},
}
