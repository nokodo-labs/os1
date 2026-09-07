import { ratchetStableViewport } from '$lib/stores/device.svelte'
import { describe, expect, it } from 'vitest'

/**
 * the wallpaper is a `position: fixed; inset: 0` layer, so it follows the LAYOUT
 * viewport - which android now shrinks for the virtual keyboard
 * (`interactive-widget=resizes-content`). the ratchet is what lets that layer
 * hold one size across a keyboard toggle while still following rotation.
 */
describe('ratchetStableViewport', () => {
	it('adopts the live size on the first sync', () => {
		expect(
			ratchetStableViewport({ width: 0, height: 0 }, { width: 400, height: 860 }, true)
		).toEqual({ width: 400, height: 860 })
	})

	it('holds the tall height while the keyboard shrinks the viewport', () => {
		// the canvas wallpapers re-seed their field on every resize, so this is the
		// difference between a stable background and one that reflows per keystroke
		expect(
			ratchetStableViewport({ width: 400, height: 860 }, { width: 400, height: 520 }, true)
		).toEqual({ width: 400, height: 860 })
	})

	it('ratchets up when the viewport grows at the same width', () => {
		// the url bar hiding on scroll: the layer may grow, it may never shrink
		expect(
			ratchetStableViewport({ width: 400, height: 800 }, { width: 400, height: 860 }, true)
		).toEqual({ width: 400, height: 860 })
	})

	it('starts over on a width change, so rotation really resizes the layer', () => {
		// portrait 400x860 -> landscape 860x400: the taller portrait height must go
		expect(
			ratchetStableViewport({ width: 400, height: 860 }, { width: 860, height: 400 }, true)
		).toEqual({ width: 860, height: 400 })
	})

	it('tracks the window exactly where nothing can overlay the viewport', () => {
		// desktop: a window dragged shorter really is shorter
		expect(
			ratchetStableViewport({ width: 1280, height: 900 }, { width: 1280, height: 600 }, false)
		).toEqual({ width: 1280, height: 600 })
	})

	it('never hands back the object it was given', () => {
		const previous = { width: 400, height: 860 }
		const next = { width: 400, height: 520 }
		const held = ratchetStableViewport(previous, next, true)
		expect(held).not.toBe(previous)
		expect(ratchetStableViewport(previous, next, false)).not.toBe(next)
	})
})
