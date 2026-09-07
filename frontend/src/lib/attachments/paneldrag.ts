/**
 * grab-to-close for a bottom panel, with the handoff a native one has:
 * a scroll that reaches the top and keeps going down becomes a drag on the
 * panel, in one gesture, with no lift-and-regrab.
 *
 * while the content still has somewhere to go the browser's own scrolling runs
 * untouched - nothing here is prevented and every listener is passive - and the
 * panel only takes over once every scroller under the finger sits at its top.
 * from then on the transform is written straight from the event handler, so the
 * panel tracks the finger 1:1: no css transition, no rAF hop, no layout read
 * between the move and the paint.
 *
 * touch travel is read from touch events on purpose. a browser cancels the
 * pointer stream the moment it starts scrolling an element, which is precisely
 * the gesture the handoff has to survive; passive `touchmove` keeps arriving
 * throughout. mouse and pen stay on the pointer path, and drag only from the
 * handle - a wheel never grabs a panel on any platform, so none is listened for.
 */

import {
	advancePanelGesture,
	beginPanelGesture,
	releasePanelGesture,
	PANEL_GESTURE_DEFAULTS,
	type PanelGestureConfig,
	type PanelGestureState,
} from '$lib/utils/panelGesture'
import type { Attachment } from 'svelte/attachments'

export interface PanelDragOptions {
	/** the release passed the point of no return - unmount the panel. */
	onDismiss: () => void
	/** settle immediately and dismiss without a flight. */
	reducedMotion?: () => boolean
	/** turn the gesture off without tearing the listeners down. */
	enabled?: boolean
	config?: Partial<PanelGestureConfig>
}

/** marks the strip a mouse or pen may start a drag from. */
export const PANEL_HANDLE_ATTRIBUTE = 'data-panel-handle'

const SETTLE_MS = 320

/**
 * a critically damped spring's tail: both y control points sit at 1, so the
 * settle decelerates into rest and can never carry momentum past it. the panel
 * is anchored on its upward side, and an overshooting curve would lift it off.
 */
const SPRING_EASING = 'cubic-bezier(0.22, 1, 0.36, 1)'
const FLY_EASING = 'cubic-bezier(0.32, 0.72, 0, 1)'

const FLY_MIN_MS = 140
const FLY_MAX_MS = 340

/** floor on the speed a flight is timed from, in px/ms. */
const FLY_MIN_SPEED = 1.2

/** extra travel past the bottom edge so nothing peeks back in. */
const FLY_CLEARANCE = 32

const SCROLLABLE_OVERFLOW = new Set(['auto', 'scroll', 'overlay'])

function scrollersUnder(target: EventTarget | null, root: HTMLElement): HTMLElement[] {
	const found: HTMLElement[] = []
	let element = target instanceof Element ? target : null
	while (element) {
		if (element instanceof HTMLElement && element.scrollHeight - element.clientHeight > 1) {
			const overflow = getComputedStyle(element).overflowY
			if (SCROLLABLE_OVERFLOW.has(overflow)) found.push(element)
		}
		if (element === root) break
		element = element.parentElement
	}
	return found
}

export function panelDrag(options: PanelDragOptions): Attachment<HTMLElement> {
	return (node) => {
		let state: PanelGestureState | null = null
		let scrollers: HTMLElement[] = []
		let touchId: number | null = null
		let pointerId: number | null = null
		let flying = false
		let clearTransition: number | undefined

		// a drag is not a tap: the click a release can still produce is swallowed
		let swallowClick = false

		const config: PanelGestureConfig = { ...PANEL_GESTURE_DEFAULTS, ...options.config }

		/** scrollers whose own scrolling is parked for the length of a drag. */
		const parked = new Map<HTMLElement, string>()
		/** containment we applied, handed back on cleanup. */
		const contained = new Map<HTMLElement, string>()

		function paint(offset: number): void {
			node.style.transform = offset === 0 ? '' : `translate3d(0, ${offset}px, 0)`
		}

		function atTop(): boolean {
			return scrollers.every((scroller) => scroller.scrollTop <= 0)
		}

		function claim(): void {
			window.clearTimeout(clearTransition)
			node.style.transition = 'none'
			node.style.willChange = 'transform'
			swallowClick = true
			// stop the browser's own scrolling dead so its overscroll bounce never
			// fights the grab. every scroller is at its top here, so nothing is lost
			for (const scroller of scrollers) {
				parked.set(scroller, scroller.style.overflowY)
				scroller.style.overflowY = 'hidden'
			}
		}

		function unpark(): void {
			for (const [scroller, overflowY] of parked) scroller.style.overflowY = overflowY
			parked.clear()
		}

		function settle(): void {
			node.style.willChange = ''
			if (options.reducedMotion?.()) {
				node.style.transition = ''
				paint(0)
				return
			}
			node.style.transition = `transform ${SETTLE_MS}ms ${SPRING_EASING}`
			paint(0)
			clearTransition = window.setTimeout(() => {
				node.style.transition = ''
			}, SETTLE_MS + 20)
		}

		function flyOut(offset: number, velocity: number): void {
			node.style.willChange = ''
			if (options.reducedMotion?.()) {
				options.onDismiss()
				return
			}
			flying = true
			// the only layout read of the whole gesture, and it happens after the
			// finger is already up
			const remaining = Math.max(
				FLY_CLEARANCE,
				node.getBoundingClientRect().height - offset + FLY_CLEARANCE
			)
			const speed = Math.max(velocity, FLY_MIN_SPEED)
			const ms = Math.min(FLY_MAX_MS, Math.max(FLY_MIN_MS, remaining / speed))
			node.style.transition = `transform ${ms}ms ${FLY_EASING}`
			paint(offset + remaining)
			window.setTimeout(() => {
				flying = false
				options.onDismiss()
			}, ms)
		}

		function start(x: number, y: number, time: number, target: EventTarget | null): void {
			swallowClick = false
			state = beginPanelGesture({ x, y, time, atTop: true })
			scrollers = scrollersUnder(target, node)
			// the handoff moment is only clean when the scroll cannot chain past
			// the panel into whatever sits behind it
			for (const scroller of scrollers) {
				if (contained.has(scroller)) continue
				contained.set(scroller, scroller.style.overscrollBehaviorY)
				scroller.style.overscrollBehaviorY = 'contain'
			}
		}

		function advance(x: number, y: number, time: number): void {
			if (!state) return
			const wasDragging = state.phase === 'dragging'
			// the scroll position only matters until the panel owns the gesture, so
			// once it does there is no layout read left in the move path at all
			const sample = { x, y, time, atTop: wasDragging || atTop() }
			state = advancePanelGesture(state, sample, config)
			if (state.phase === 'abandoned') {
				state = null
				return
			}
			if (state.phase !== 'dragging') return
			if (!wasDragging) claim()
			paint(state.offset)
		}

		function end(): void {
			const finished = state
			state = null
			unpark()
			if (!finished || finished.phase !== 'dragging') return
			const release = releasePanelGesture(finished, config)
			if (release.action === 'dismiss') {
				flyOut(finished.offset, release.velocity)
				return
			}
			settle()
		}

		function cancel(): void {
			const wasDragging = state?.phase === 'dragging'
			state = null
			touchId = null
			pointerId = null
			unpark()
			if (wasDragging) settle()
		}

		function onTouchStart(event: TouchEvent): void {
			if (options.enabled === false || flying) return
			if (touchId !== null || event.touches.length !== 1) {
				// a second finger means a pinch or something else entirely
				cancel()
				return
			}
			const touch = event.changedTouches[0]
			if (!touch) return
			touchId = touch.identifier
			start(touch.clientX, touch.clientY, event.timeStamp, event.target)
		}

		function trackedTouch(event: TouchEvent): Touch | null {
			if (touchId === null) return null
			for (let index = 0; index < event.changedTouches.length; index += 1) {
				const touch = event.changedTouches.item(index)
				if (touch && touch.identifier === touchId) return touch
			}
			return null
		}

		function onTouchMove(event: TouchEvent): void {
			const touch = trackedTouch(event)
			if (!touch) return
			advance(touch.clientX, touch.clientY, event.timeStamp)
		}

		function onTouchEnd(event: TouchEvent): void {
			if (!trackedTouch(event)) return
			touchId = null
			end()
		}

		function onTouchCancel(event: TouchEvent): void {
			if (!trackedTouch(event)) return
			cancel()
		}

		function onPointerDown(event: PointerEvent): void {
			if (options.enabled === false || flying) return
			// touch runs on the touch path, which survives a native scroll
			if (event.pointerType === 'touch' || pointerId !== null) return
			// a mouse drags a panel by its handle only, so selecting text and
			// pressing controls inside the panel keep working
			if (
				!(event.target instanceof Element) ||
				!event.target.closest(`[${PANEL_HANDLE_ATTRIBUTE}]`)
			)
				return
			pointerId = event.pointerId
			node.setPointerCapture(event.pointerId)
			start(event.clientX, event.clientY, event.timeStamp, event.target)
		}

		function onPointerMove(event: PointerEvent): void {
			if (pointerId !== event.pointerId) return
			advance(event.clientX, event.clientY, event.timeStamp)
		}

		function onPointerUp(event: PointerEvent): void {
			if (pointerId !== event.pointerId) return
			pointerId = null
			end()
		}

		function onPointerCancel(event: PointerEvent): void {
			if (pointerId !== event.pointerId) return
			cancel()
		}

		function onClick(event: MouseEvent): void {
			if (!swallowClick) return
			swallowClick = false
			event.preventDefault()
			event.stopImmediatePropagation()
		}

		node.addEventListener('touchstart', onTouchStart, { passive: true })
		node.addEventListener('touchmove', onTouchMove, { passive: true })
		node.addEventListener('touchend', onTouchEnd, { passive: true })
		node.addEventListener('touchcancel', onTouchCancel, { passive: true })
		node.addEventListener('pointerdown', onPointerDown, { passive: true })
		node.addEventListener('pointermove', onPointerMove, { passive: true })
		node.addEventListener('pointerup', onPointerUp, { passive: true })
		node.addEventListener('pointercancel', onPointerCancel, { passive: true })
		node.addEventListener('click', onClick, true)

		return () => {
			window.clearTimeout(clearTransition)
			unpark()
			for (const [scroller, value] of contained) scroller.style.overscrollBehaviorY = value
			contained.clear()
			node.removeEventListener('touchstart', onTouchStart)
			node.removeEventListener('touchmove', onTouchMove)
			node.removeEventListener('touchend', onTouchEnd)
			node.removeEventListener('touchcancel', onTouchCancel)
			node.removeEventListener('pointerdown', onPointerDown)
			node.removeEventListener('pointermove', onPointerMove)
			node.removeEventListener('pointerup', onPointerUp)
			node.removeEventListener('pointercancel', onPointerCancel)
			node.removeEventListener('click', onClick, true)
		}
	}
}
