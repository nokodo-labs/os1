import {
	fitInside,
	MENU_EDGE_MARGIN,
	placeBelow,
	placeBeside,
} from '$lib/components/primitives/menuPlacement'
import { describe, expect, it } from 'vitest'

const anchor = (rect: Partial<{ top: number; bottom: number; left: number; right: number }>) => ({
	top: 0,
	bottom: 0,
	left: 0,
	right: 0,
	...rect,
})

describe('fitInside', () => {
	it('leaves an offset that already fits alone', () => {
		expect(fitInside(100, 200, 800)).toBe(100)
	})

	it('pulls an overflowing menu back inside the viewport', () => {
		expect(fitInside(700, 200, 800)).toBe(800 - 200 - MENU_EDGE_MARGIN)
	})

	it('keeps the edge margin when the menu is wider than the viewport', () => {
		expect(fitInside(40, 900, 800)).toBe(MENU_EDGE_MARGIN)
	})
})

describe('placeBelow', () => {
	it('drops below the anchor when there is room', () => {
		expect(placeBelow(anchor({ top: 100, bottom: 130 }), 200, 800, 4)).toBe(134)
	})

	it('flips above the anchor when the menu does not fit below', () => {
		expect(placeBelow(anchor({ top: 600, bottom: 630 }), 200, 800, 4)).toBe(396)
	})

	it('clamps when neither side has room', () => {
		expect(placeBelow(anchor({ top: 180, bottom: 210 }), 400, 500, 4)).toBe(
			500 - 400 - MENU_EDGE_MARGIN
		)
	})
})

describe('placeBeside', () => {
	it('opens to the right of the anchor when there is room', () => {
		expect(placeBeside(anchor({ left: 100, right: 260 }), 240, 1000, 6)).toBe(266)
	})

	it('flips to the left of the anchor near the right edge', () => {
		expect(placeBeside(anchor({ left: 700, right: 860 }), 240, 1000, 6)).toBe(454)
	})

	it('stays inside a viewport too narrow for either side', () => {
		// the compact case: submenu overlaps its parent instead of running off screen
		expect(placeBeside(anchor({ left: 224, right: 392 }), 246, 416, 6)).toBe(
			416 - 246 - MENU_EDGE_MARGIN
		)
	})
})
