/**
 * the lift's fitting arithmetic (F137): a bubble held half off the screen has to
 * come back onto it, ensemble and all, and one taller than the screen has to
 * decide which end it keeps.
 */

import { clampSpan, fitTranslation, liftEnsembleBox, type SafeArea } from '$lib/chat/liftGeometry'
import { describe, expect, it } from 'vitest'

/** a phone-ish viewport with the island above and the composer below. */
const SAFE: SafeArea = { top: 100, bottom: 700, left: 12, right: 388 }

/** the ensemble a right-aligned bubble draws: a stamp above, three floats beside. */
function ensemble(left: number, top: number, width: number, height: number) {
	return {
		rect: { left, top, width, height },
		scale: 1.07,
		stampHeight: 16,
		stampGap: 22,
		floatsWidth: 32,
		floatsHeight: 112,
		floatGap: 10,
		align: 'right' as const,
	}
}

describe('lift ensemble box', () => {
	it('grows the bubble about its centre and takes in the stamp and the floats', () => {
		const box = liftEnsembleBox(ensemble(200, 300, 100, 200))

		// 200 * 0.07 / 2 = 7 of growth each way, then 22 + 16 for the stamp
		expect(box.top).toBeCloseTo(300 - 7 - 38, 5)
		expect(box.height).toBeCloseTo(200 + 14 + 38, 5)
		// the column hangs off the outer edge: 10 of gap plus its own 32
		expect(box.left).toBeCloseTo(200 - 42, 5)
	})

	it('lets a short bubble be measured by the column beside it, not by itself', () => {
		const box = liftEnsembleBox(ensemble(200, 300, 60, 30))

		// the 112-tall column overhangs a 30-tall bubble at both ends
		expect(box.top + box.height).toBeCloseTo(315 + 56, 5)
	})

	it('hangs the column off the other side for an incoming bubble', () => {
		const box = liftEnsembleBox({ ...ensemble(200, 300, 100, 60), align: 'left' })

		expect(box.left).toBeCloseTo(200 - 3.5, 5)
		expect(box.left + box.width).toBeCloseTo(300 + 42, 5)
	})
})

describe('fit translation', () => {
	it('leaves an ensemble that already fits exactly where it is', () => {
		expect(fitTranslation({ left: 100, top: 300, width: 200, height: 200 }, SAFE)).toEqual({
			x: 0,
			y: 0,
		})
	})

	it('pushes a bubble scrolled under the island back down', () => {
		const shift = fitTranslation({ left: 100, top: 40, width: 200, height: 200 }, SAFE)

		expect(shift.y).toBe(60)
		expect(shift.x).toBe(0)
	})

	it('lifts a bubble sitting on the composer back up', () => {
		const shift = fitTranslation({ left: 100, top: 600, width: 200, height: 200 }, SAFE)

		expect(shift.y).toBe(-100)
	})

	it('moves an ensemble hanging off an edge back inside', () => {
		expect(fitTranslation({ left: -20, top: 300, width: 200, height: 100 }, SAFE).x).toBe(32)
		expect(fitTranslation({ left: 300, top: 300, width: 200, height: 100 }, SAFE).x).toBe(-112)
	})

	it('pins the TOP of a bubble taller than the screen, and lets the rest run off', () => {
		// 900 tall against 600 of room: the head is what the reader is holding
		const shift = fitTranslation({ left: 100, top: 250, width: 200, height: 900 }, SAFE)

		expect(shift.y).toBe(SAFE.top - 250)
		expect(250 + shift.y).toBe(SAFE.top)
	})

	it('pins the top even when the bubble already starts above the safe area', () => {
		const shift = fitTranslation({ left: 100, top: -400, width: 200, height: 900 }, SAFE)

		expect(-400 + shift.y).toBe(SAFE.top)
	})
})

describe('clamped spans', () => {
	it('leaves a span that fits alone', () => {
		expect(clampSpan(150, 90, 12, 388)).toBe(150)
	})

	it('slides a span back off both edges', () => {
		expect(clampSpan(-30, 90, 12, 388)).toBe(12)
		expect(clampSpan(340, 90, 12, 388)).toBe(388 - 90)
	})

	it('centres a span with nowhere to fit, so it spills evenly rather than one way', () => {
		expect(clampSpan(0, 500, 12, 388)).toBe(12 + (376 - 500) / 2)
	})
})
