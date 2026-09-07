/**
 * the decision layer of a bottom panel's grab-to-close gesture.
 *
 * kept free of the dom so the handoff rule can be reasoned about on its own:
 * while the content under the finger still has somewhere to scroll the panel
 * stays put, and the moment every scroller sits at its top and the finger keeps
 * going down the same gesture becomes a drag on the panel itself.
 *
 * the origin is rebased on every sample the panel does not own, so the drag
 * starts from where the content ran out rather than from where the finger first
 * landed - that is what makes the takeover read as one continuous motion
 * instead of a jump.
 */

export type PanelGesturePhase = 'scrolling' | 'dragging' | 'abandoned'

export interface PanelGestureConfig {
	/** downward travel past the top before the panel takes the gesture, in px. */
	claimDistance: number
	/** sideways travel that means the gesture belongs to something else, in px. */
	crossCancel: number
	/** travel, after momentum projection, that closes the panel, in px. */
	dismissDistance: number
	/** speed that decides a release on its own, in px/ms. */
	flickVelocity: number
	/** how far ahead a release's momentum is projected, in ms. */
	projectionMs: number
}

export const PANEL_GESTURE_DEFAULTS: PanelGestureConfig = {
	claimDistance: 8,
	crossCancel: 16,
	dismissDistance: 96,
	flickVelocity: 0.55,
	projectionMs: 140,
}

export interface PanelGestureState {
	phase: PanelGesturePhase
	/** y the drag measures from; rebased for as long as the content scrolls. */
	originY: number
	startX: number
	/** displacement from rest, in px. positive is downward, toward dismissal. */
	offset: number
	lastY: number
	lastTime: number
	/** the sample before `last`, which is what a release reads its speed from. */
	previousY: number
	previousTime: number
}

export interface PanelGestureSample {
	x: number
	y: number
	/** monotonic ms; only differences are used. */
	time: number
	/** true only when every scroller under the pointer sits at its top. */
	atTop: boolean
}

export type PanelReleaseAction = 'dismiss' | 'settle'

export interface PanelGestureRelease {
	action: PanelReleaseAction
	/** downward speed at release, in px/ms. */
	velocity: number
	/** where the momentum would carry the panel, in px. */
	projected: number
}

export function beginPanelGesture(sample: PanelGestureSample): PanelGestureState {
	return {
		phase: 'scrolling',
		originY: sample.y,
		startX: sample.x,
		offset: 0,
		lastY: sample.y,
		lastTime: sample.time,
		previousY: sample.y,
		previousTime: sample.time,
	}
}

function withSample(state: PanelGestureState, sample: PanelGestureSample): PanelGestureState {
	return {
		...state,
		previousY: state.lastY,
		previousTime: state.lastTime,
		lastY: sample.y,
		lastTime: sample.time,
	}
}

export function advancePanelGesture(
	state: PanelGestureState,
	sample: PanelGestureSample,
	config: PanelGestureConfig = PANEL_GESTURE_DEFAULTS
): PanelGestureState {
	if (state.phase === 'abandoned') return state

	const next = withSample(state, sample)

	if (state.phase === 'dragging') {
		// the panel is anchored at its resting position: it is only ever dragged
		// downward, toward dismissal. travel above rest stops dead at zero, so a
		// drag that reverses upward can never lift the panel off its anchor and
		// expose the cut-off bottom edge beneath it
		next.offset = Math.max(0, sample.y - state.originY)
		return next
	}

	const dy = sample.y - state.originY
	const dx = sample.x - state.startX
	if (Math.abs(dx) > config.crossCancel && Math.abs(dx) > Math.abs(dy)) {
		return { ...next, phase: 'abandoned' }
	}

	// the content is still moving under the finger, or the finger is heading the
	// other way: the panel is not involved, and the drag would start from here
	if (!sample.atTop || dy <= 0) {
		next.originY = sample.y
		return next
	}

	if (dy < config.claimDistance) return next

	// handoff. the claim distance is folded into the origin so the panel picks
	// the finger up at zero displacement and tracks it 1:1 from there
	next.phase = 'dragging'
	next.originY = state.originY + config.claimDistance
	next.offset = dy - config.claimDistance
	// speed is measured from the takeover onward, so a release right after a
	// fast scroll is judged on the drag's own momentum and not the scroll's
	next.previousY = sample.y
	next.previousTime = sample.time
	return next
}

export function releasePanelGesture(
	state: PanelGestureState,
	config: PanelGestureConfig = PANEL_GESTURE_DEFAULTS
): PanelGestureRelease {
	if (state.phase !== 'dragging') return { action: 'settle', velocity: 0, projected: 0 }

	const elapsed = state.lastTime - state.previousTime
	const velocity = elapsed > 0 ? (state.lastY - state.previousY) / elapsed : 0
	const projected = state.offset + velocity * config.projectionMs

	// a flick decides on its own, in either direction: a hard throw down closes
	// from anywhere, and a throw back up keeps the panel even from past the line
	if (velocity <= -config.flickVelocity) return { action: 'settle', velocity, projected }
	if (velocity >= config.flickVelocity) return { action: 'dismiss', velocity, projected }

	return {
		action: projected >= config.dismissDistance ? 'dismiss' : 'settle',
		velocity,
		projected,
	}
}
