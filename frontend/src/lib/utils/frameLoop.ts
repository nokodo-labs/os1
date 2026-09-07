// one shared, visibility-aware animation frame loop.
//
// - drives `render` from requestAnimationFrame while the document is visible
// - pauses while it is hidden, and resumes without a dt spike: the hidden gap
//   never reaches the clock, so time-based shaders keep their phase
// - `maxFps` skips frames with a time accumulator (no timers) to cap the rate

export type FrameLoopRender = (nowMs: number, dtMs: number) => void

export interface FrameLoopOptions {
	/** cap on rendered frames per second. omit to render on every animation frame. */
	maxFps?: number
}

/** longest gap a single frame may contribute, so a stall cannot jump the clock. */
const MAX_FRAME_DT_MS = 100

/**
 * start a frame loop that only runs while the document is visible.
 *
 * `nowMs` is the loop clock: milliseconds elapsed since the first frame,
 * excluding any time the document spent hidden. `dtMs` is the gap since the
 * previous rendered frame (0 on the first frame and on each resume).
 *
 * returns a stop function; calling it more than once is a no-op.
 */
export function startFrameLoop(
	render: FrameLoopRender,
	options: FrameLoopOptions = {}
): () => void {
	if (typeof requestAnimationFrame !== 'function' || typeof document === 'undefined') {
		return () => {}
	}

	const { maxFps } = options
	const minFrameMs = maxFps !== undefined && maxFps > 0 ? 1000 / maxFps : 0
	const maxDtMs = Math.max(MAX_FRAME_DT_MS, minFrameMs * 2)

	let frameId: number | null = null
	let stopped = false
	let lastTimestamp: number | null = null
	let clockMs = 0
	let lastRenderMs = 0
	let pendingMs = 0

	function tick(timestamp: number): void {
		frameId = requestAnimationFrame(tick)

		const previous = lastTimestamp
		lastTimestamp = timestamp

		const dtMs = previous === null ? 0 : Math.min(Math.max(timestamp - previous, 0), maxDtMs)
		clockMs += dtMs
		pendingMs += dtMs

		// a resumed loop always paints immediately; otherwise honour the fps cap
		if (previous !== null && pendingMs < minFrameMs) return
		pendingMs = previous === null ? 0 : Math.min(pendingMs - minFrameMs, minFrameMs)

		const renderDtMs = clockMs - lastRenderMs
		lastRenderMs = clockMs
		render(clockMs, renderDtMs)
	}

	function handleVisibility(): void {
		if (stopped) return
		if (document.visibilityState === 'visible') {
			if (frameId !== null) return
			// drop the hidden gap instead of feeding it to the next frame
			lastTimestamp = null
			frameId = requestAnimationFrame(tick)
		} else if (frameId !== null) {
			cancelAnimationFrame(frameId)
			frameId = null
		}
	}

	document.addEventListener('visibilitychange', handleVisibility)
	handleVisibility()

	return () => {
		if (stopped) return
		stopped = true
		document.removeEventListener('visibilitychange', handleVisibility)
		if (frameId !== null) {
			cancelAnimationFrame(frameId)
			frameId = null
		}
	}
}

/** observe document visibility with the same rule the frame loop uses. */
export function onVisibilityChange(onChange: (visible: boolean) => void): () => void {
	if (typeof document === 'undefined') return () => {}

	const handle = () => onChange(document.visibilityState === 'visible')
	document.addEventListener('visibilitychange', handle)
	return () => document.removeEventListener('visibilitychange', handle)
}
