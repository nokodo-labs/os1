import {
	advancePanelGesture,
	beginPanelGesture,
	releasePanelGesture,
	PANEL_GESTURE_DEFAULTS,
	type PanelGestureSample,
	type PanelGestureState,
} from '$lib/utils/panelGesture'
import { describe, expect, it } from 'vitest'

const START_X = 100
const START_Y = 400
const FRAME = 16

function begin(): PanelGestureState {
	return beginPanelGesture({ x: START_X, y: START_Y, time: 0, atTop: true })
}

/** replay a run of samples through the machine, one frame apart. */
function replay(
	state: PanelGestureState,
	samples: readonly (Partial<PanelGestureSample> & { y: number })[]
): PanelGestureState {
	let current = state
	let time = current.lastTime
	for (const sample of samples) {
		time += sample.time ?? FRAME
		current = advancePanelGesture(current, {
			x: sample.x ?? START_X,
			y: sample.y,
			time,
			atTop: sample.atTop ?? true,
		})
	}
	return current
}

describe('panelGesture handoff', () => {
	it('starts in the scrolling phase, owning nothing', () => {
		const state = begin()
		expect(state.phase).toBe('scrolling')
		expect(state.offset).toBe(0)
	})

	it('takes the gesture when the content is at the top and the finger keeps going down', () => {
		const state = replay(begin(), [{ y: START_Y + 4 }, { y: START_Y + 30 }])
		expect(state.phase).toBe('dragging')
		expect(state.offset).toBe(30 - PANEL_GESTURE_DEFAULTS.claimDistance)
	})

	it('never takes the gesture while the content still has somewhere to scroll', () => {
		const state = replay(begin(), [
			{ y: START_Y + 40, atTop: false },
			{ y: START_Y + 120, atTop: false },
			{ y: START_Y + 300, atTop: false },
		])
		expect(state.phase).toBe('scrolling')
		expect(state.offset).toBe(0)
	})

	it('hands off mid-gesture, measuring the drag from where the content ran out', () => {
		// 200px of content scrolled by, then the scroller hits its top and the
		// finger carries on for 50px more: the panel moves by that 50px, not 250
		const state = replay(begin(), [
			{ y: START_Y + 200, atTop: false },
			{ y: START_Y + 210 },
			{ y: START_Y + 250 },
		])
		expect(state.phase).toBe('dragging')
		expect(state.offset).toBe(50 - PANEL_GESTURE_DEFAULTS.claimDistance)
	})

	it('picks the finger up at zero displacement, so the takeover never jumps', () => {
		const state = replay(begin(), [{ y: START_Y + PANEL_GESTURE_DEFAULTS.claimDistance }])
		expect(state.phase).toBe('dragging')
		expect(state.offset).toBe(0)
	})

	it('stays out of the way of an upward drag at the top', () => {
		const state = replay(begin(), [{ y: START_Y - 40 }, { y: START_Y - 90 }])
		expect(state.phase).toBe('scrolling')
	})

	it('rebases on an upward drag, so a reversal at the top still hands off', () => {
		const state = replay(begin(), [{ y: START_Y - 90 }, { y: START_Y - 60 }])
		expect(state.phase).toBe('dragging')
		expect(state.offset).toBe(30 - PANEL_GESTURE_DEFAULTS.claimDistance)
	})

	it('stops dead at rest instead of riding above its anchor', () => {
		const dragging = replay(begin(), [{ y: START_Y + 60 }])
		const lifted = replay(dragging, [{ y: START_Y - 40 }])
		expect(lifted.offset).toBe(0)
	})

	it('clamps at rest through a drag down and a hard flick back up', () => {
		// the reported defect: one motion down then far up lifted the whole panel
		// off its anchor and exposed the cut-off edge underneath it
		const flicked = replay(begin(), [
			{ y: START_Y + 40 },
			{ y: START_Y + 120 },
			{ y: START_Y + 60 },
			{ y: START_Y - 200 },
			{ y: START_Y - 400 },
		])
		expect(flicked.offset).toBe(0)
		// and the release must settle it there, not throw it further up
		expect(releasePanelGesture(flicked).action).toBe('settle')
	})

	it('comes back down 1:1 after being pushed against the anchor', () => {
		const pinned = replay(begin(), [{ y: START_Y + 60 }, { y: START_Y - 300 }])
		expect(pinned.offset).toBe(0)
		const returned = replay(pinned, [{ y: START_Y + 90 }])
		expect(returned.offset).toBe(90 - PANEL_GESTURE_DEFAULTS.claimDistance)
	})

	it('hands a sideways gesture back untouched', () => {
		const state = replay(begin(), [{ x: START_X + 60, y: START_Y + 10 }])
		expect(state.phase).toBe('abandoned')
		expect(
			advancePanelGesture(state, { x: START_X, y: START_Y + 400, time: 999, atTop: true })
		).toBe(state)
	})

	it('keeps a mostly-vertical gesture that drifts sideways', () => {
		const state = replay(begin(), [{ x: START_X + 20, y: START_Y + 60 }])
		expect(state.phase).toBe('dragging')
	})
})

describe('panelGesture release', () => {
	/** drag the panel at a steady `perFrame` px per frame, for `frames` frames. */
	function dragBy(perFrame: number, frames: number): PanelGestureState {
		const claimed = replay(begin(), [{ y: START_Y + PANEL_GESTURE_DEFAULTS.claimDistance }])
		const steps = Array.from({ length: frames }, (_, index) => ({
			y: START_Y + PANEL_GESTURE_DEFAULTS.claimDistance + (index + 1) * perFrame,
		}))
		return replay(claimed, steps)
	}

	it('settles a gesture the panel never owned', () => {
		const release = releasePanelGesture(begin())
		expect(release.action).toBe('settle')
		expect(release.velocity).toBe(0)
	})

	it('dismisses a slow drag taken past the threshold', () => {
		const dragged = dragBy(8, 15)
		expect(dragged.offset).toBeGreaterThan(PANEL_GESTURE_DEFAULTS.dismissDistance)
		expect(releasePanelGesture(dragged).action).toBe('dismiss')
	})

	it('settles a short slow drag', () => {
		expect(releasePanelGesture(dragBy(4, 8)).action).toBe('settle')
	})

	it('dismisses a short fast flick on speed alone', () => {
		const flicked = dragBy(30, 2)
		const release = releasePanelGesture(flicked)
		expect(flicked.offset).toBeLessThan(PANEL_GESTURE_DEFAULTS.dismissDistance)
		expect(release.velocity).toBeGreaterThan(PANEL_GESTURE_DEFAULTS.flickVelocity)
		expect(release.action).toBe('dismiss')
	})

	it('keeps the panel when a drag past the threshold is thrown back up', () => {
		const dragged = dragBy(8, 17)
		expect(dragged.offset).toBeGreaterThan(PANEL_GESTURE_DEFAULTS.dismissDistance)
		const thrownBack = replay(dragged, [{ y: dragged.lastY - 30 }])
		const release = releasePanelGesture(thrownBack)
		expect(release.velocity).toBeLessThan(-PANEL_GESTURE_DEFAULTS.flickVelocity)
		expect(release.action).toBe('settle')
	})

	it('projects momentum, so a drag short of the line still closes when thrown', () => {
		const dragged = dragBy(8, 10)
		const release = releasePanelGesture(dragged)
		expect(dragged.offset).toBeLessThan(PANEL_GESTURE_DEFAULTS.dismissDistance)
		expect(release.velocity).toBeLessThan(PANEL_GESTURE_DEFAULTS.flickVelocity)
		expect(release.projected).toBeGreaterThan(PANEL_GESTURE_DEFAULTS.dismissDistance)
		expect(release.action).toBe('dismiss')
	})
})
