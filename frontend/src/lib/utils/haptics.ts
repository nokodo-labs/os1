/**
 * haptic feedback utilities for supported devices.
 */

import { browser } from '$app/environment'
import { preferences } from '$lib/stores/preferences.svelte'

/**
 * triggers a short haptic vibration if the device supports it and the setting is enabled.
 * uses a very brief 5ms pulse for subtle feedback on incoming agent deltas.
 */
export function hapticFeedback(): void {
	if (!browser) return
	if (!preferences.data.accessibility.hapticFeedback) return
	if (typeof navigator.vibrate !== 'function') return
	navigator.vibrate(5)
}
