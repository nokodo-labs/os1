import { visualViewportOvershoot } from '$lib/stores/device.svelte'
import { describe, expect, it } from 'vitest'

/**
 * the chat composer is pinned to the bottom of a layout-viewport-sized shell.
 * in-browser android keeps that viewport full-height when the keyboard opens, so
 * the overhang below the VISUAL viewport is what has to be given back.
 */
describe('visualViewportOvershoot', () => {
	it('is zero when the visible viewport still reaches the element bottom', () => {
		// desktop / standalone: nothing overlays the viewport
		expect(visualViewportOvershoot(800, 800, 0)).toBe(0)
	})

	it('reports the keyboard overlap when only the visual viewport shrank', () => {
		// android in-browser: layout viewport stays 800, keyboard takes 320
		expect(visualViewportOvershoot(800, 480, 0)).toBe(320)
	})

	it('reports the leftover overlap once --app-height has clamped the shell', () => {
		// shell already resized to the visual viewport: nothing left to correct
		expect(visualViewportOvershoot(480, 480, 0)).toBe(0)
		// shell only partly clamped (stale by 40px) - lift by the remainder
		expect(visualViewportOvershoot(520, 480, 0)).toBe(40)
	})

	it('counts a scrolled visual viewport as extra room below the element', () => {
		// ios: the browser scrolled the visual viewport down to reveal the caret,
		// so the shell bottom is already above the fold - never push it down
		expect(visualViewportOvershoot(480, 480, 60)).toBe(0)
		// still overlapping despite the scroll
		expect(visualViewportOvershoot(700, 480, 60)).toBe(160)
	})

	it('rounds to whole pixels', () => {
		expect(visualViewportOvershoot(800.4, 479.7, 0)).toBe(321)
	})

	it('falls back to zero on missing or degenerate metrics', () => {
		expect(visualViewportOvershoot(Number.NaN, 480, 0)).toBe(0)
		expect(visualViewportOvershoot(800, Number.NaN, 0)).toBe(0)
		expect(visualViewportOvershoot(800, 0, 0)).toBe(0)
		expect(visualViewportOvershoot(800, 480, Number.NaN)).toBe(320)
	})
})
