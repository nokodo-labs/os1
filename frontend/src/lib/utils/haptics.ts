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
	navigator.vibrate(1)
}

// ── throttled variant for streaming text chunks ────────────

const HAPTIC_THROTTLE_MS = 15
let lastHapticTime = 0

/**
 * throttled haptic feedback for streaming text deltas.
 * fires at most once per HAPTIC_THROTTLE_MS to avoid excessive vibration
 * while still giving tactile feedback during token delivery.
 */
export function throttledHapticFeedback(): void {
	const now = performance.now()
	if (now - lastHapticTime < HAPTIC_THROTTLE_MS) return
	lastHapticTime = now
	hapticFeedback()
}
