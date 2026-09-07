/**
 * directional swipe-to-act on a row, bubble, or button (whatsapp-style reply,
 * a swipe-up on a send button, a swipe-away dismissal).
 *
 * the element follows the finger with rubber-band resistance and snaps back on
 * release; crossing the threshold fires the action once. travel in a direction
 * the caller did not ask for is handed straight back, so a swipe never fights
 * a scroll. dismissals can fly the element off-screen instead of snapping, and
 * only then hand over, so the caller can unmount on `onTrigger`.
 */

import type { Attachment } from 'svelte/attachments'

export type SwipeDirection = 'left' | 'right' | 'up' | 'down'

export interface SwipeOptions {
	/** fired once when the gesture passes the threshold and is released. */
	onTrigger: (direction: SwipeDirection) => void
	/** which way (or ways) the finger travels to arm the action. */
	direction?: SwipeDirection | readonly SwipeDirection[]
	/** px of travel required to arm the action. */
	threshold?: number
	/** hard cap on travel in px, after damping. omit for an unbounded rubber-band. */
	maxTravel?: number
	/** disable without tearing down the listeners (e.g. read-only threads). */
	enabled?: boolean
	/** what an armed release does: snap back, or fly off-screen and fade out. */
	release?: 'snap' | 'fly'
	/** the gesture was claimed - callers pause timers here. */
	onGrab?: () => void
	/** the pointer let go without triggering - the counterpart to `onGrab`. */
	onRelease?: () => void
	/** notified as the element is dragged, so callers can render an affordance. */
	onProgress?: (progress: number, direction: SwipeDirection) => void
}

const DEFAULT_THRESHOLD = 64

/** past this much travel across the axis the gesture belongs to something else. */
const CROSS_CANCEL = 12

/** resistance applied beyond the threshold so the element feels anchored. */
const OVERSHOOT_DAMPING = 0.35

/** how far the finger must travel along the axis before claiming the gesture. */
const CLAIM_DISTANCE = 10

const SNAP_MS = 220
const FLY_MS = 260

/** extra travel past the viewport edge so nothing peeks back in. */
const FLY_CLEARANCE = 24

function isHorizontal(direction: SwipeDirection): boolean {
	return direction === 'left' || direction === 'right'
}

function transformFor(direction: SwipeDirection, distance: number): string {
	switch (direction) {
		case 'left':
			return `translateX(${-distance}px)`
		case 'right':
			return `translateX(${distance}px)`
		case 'up':
			return `translateY(${-distance}px)`
		case 'down':
			return `translateY(${distance}px)`
	}
}

export function swipe(options: SwipeOptions): Attachment<HTMLElement> {
	return (node) => {
		const requested = options.direction ?? 'right'
		const allowed = typeof requested === 'string' ? [requested] : requested
		const fallbackDirection = allowed[0] ?? 'right'
		let pointerId: number | null = null
		let startX = 0
		let startY = 0
		// null until the gesture is classified, so an unclassified move does nothing
		let claimed: SwipeDirection | null = null
		let offset = 0
		let flying = false
		// a drag is not a tap: the click a release can still produce is swallowed.
		let swallowClick = false

		// everything we paint is handed back on cleanup, so a recycled node
		// (virtual lists reuse them) never inherits a half-finished swipe.
		const previous = {
			touchAction: node.style.touchAction,
			transform: node.style.transform,
			transition: node.style.transition,
			opacity: node.style.opacity,
		}

		// leave the untouched axis to the browser, claim ours so a pan never
		// cancels the pointer mid-swipe.
		const horizontal = allowed.some(isHorizontal)
		const vertical = allowed.some((direction) => !isHorizontal(direction))
		node.style.touchAction = horizontal && vertical ? 'none' : horizontal ? 'pan-y' : 'pan-x'

		function threshold(): number {
			return options.threshold ?? DEFAULT_THRESHOLD
		}

		function paint(value: number): void {
			const direction = claimed ?? fallbackDirection
			node.style.transform = value === 0 ? '' : transformFor(direction, value)
			options.onProgress?.(Math.min(1, value / threshold()), direction)
		}

		function settle(): void {
			node.style.transition = `transform ${SNAP_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`
			paint(0)
			offset = 0
			window.setTimeout(() => {
				node.style.transition = ''
			}, SNAP_MS + 20)
		}

		function flyOut(direction: SwipeDirection): void {
			flying = true
			const rect = node.getBoundingClientRect()
			const distance =
				direction === 'left'
					? rect.right + FLY_CLEARANCE
					: direction === 'right'
						? window.innerWidth - rect.left + FLY_CLEARANCE
						: direction === 'up'
							? rect.bottom + FLY_CLEARANCE
							: window.innerHeight - rect.top + FLY_CLEARANCE

			node.style.transition = `transform ${FLY_MS}ms ease-out, opacity ${FLY_MS}ms ease-out`
			node.style.transform = transformFor(direction, distance)
			node.style.opacity = '0'

			let handed = false
			function hand(event?: TransitionEvent): void {
				// a child's transition bubbles through here too; only ours ends the flight
				if (event && event.target !== node) return
				if (handed) return
				handed = true
				node.removeEventListener('transitionend', hand)
				window.clearTimeout(guard)
				options.onTrigger(direction)
			}
			node.addEventListener('transitionend', hand)
			// transitions do not fire when the element is off-screen or hidden
			const guard = window.setTimeout(hand, FLY_MS + 60)
		}

		function reset(): void {
			pointerId = null
			claimed = null
			offset = 0
		}

		function onPointerDown(event: PointerEvent): void {
			if (options.enabled === false || flying) return
			// mouse drags are not a swipe affordance; touch and pen only
			if (event.pointerType === 'mouse') return
			if (pointerId !== null) return
			pointerId = event.pointerId
			startX = event.clientX
			startY = event.clientY
			claimed = null
			offset = 0
		}

		function onPointerMove(event: PointerEvent): void {
			if (pointerId !== event.pointerId) return
			const dx = event.clientX - startX
			const dy = event.clientY - startY
			let direction = claimed

			if (direction === null) {
				const sideways = Math.abs(dx) >= Math.abs(dy)
				const along = sideways ? Math.abs(dx) : Math.abs(dy)
				const across = sideways ? Math.abs(dy) : Math.abs(dx)
				if (across > CROSS_CANCEL) {
					// the user is doing something else: hand the gesture back untouched
					reset()
					return
				}
				if (along < CLAIM_DISTANCE) return
				const candidate: SwipeDirection = sideways
					? dx > 0
						? 'right'
						: 'left'
					: dy > 0
						? 'down'
						: 'up'
				if (!allowed.includes(candidate)) {
					// not a direction we were asked for; leave it for other affordances
					reset()
					return
				}
				direction = candidate
				claimed = candidate
				swallowClick = true
				// the element follows the finger: no css transition may smooth that
				node.style.transition = 'none'
				options.onGrab?.()
			}

			const along = isHorizontal(direction)
				? direction === 'right'
					? dx
					: -dx
				: direction === 'down'
					? dy
					: -dy
			if (along <= 0) {
				offset = 0
				paint(0)
				return
			}

			const limit = threshold()
			// beyond the threshold the element resists, signalling "this is as far as it goes"
			offset = along <= limit ? along : limit + (along - limit) * OVERSHOOT_DAMPING
			if (options.maxTravel !== undefined) offset = Math.min(offset, options.maxTravel)
			paint(offset)
		}

		function onPointerUp(event: PointerEvent): void {
			if (pointerId !== event.pointerId) return
			const direction = claimed
			const armed = direction !== null && offset >= threshold()
			reset()
			if (direction === null || !armed) {
				settle()
				if (direction !== null) options.onRelease?.()
				return
			}
			if (options.release === 'fly') {
				flyOut(direction)
				return
			}
			settle()
			options.onTrigger(direction)
		}

		function onClick(event: MouseEvent): void {
			if (!swallowClick) return
			swallowClick = false
			event.preventDefault()
			event.stopImmediatePropagation()
		}

		function onPointerCancel(event: PointerEvent): void {
			if (pointerId !== event.pointerId) return
			const wasClaimed = claimed !== null
			reset()
			settle()
			if (wasClaimed) options.onRelease?.()
		}

		node.addEventListener('pointerdown', onPointerDown, { passive: true })
		node.addEventListener('pointermove', onPointerMove, { passive: true })
		node.addEventListener('pointerup', onPointerUp)
		node.addEventListener('pointercancel', onPointerCancel)
		node.addEventListener('click', onClick, true)

		return () => {
			node.style.touchAction = previous.touchAction
			node.style.transform = previous.transform
			node.style.transition = previous.transition
			node.style.opacity = previous.opacity
			node.removeEventListener('pointerdown', onPointerDown)
			node.removeEventListener('pointermove', onPointerMove)
			node.removeEventListener('pointerup', onPointerUp)
			node.removeEventListener('pointercancel', onPointerCancel)
			node.removeEventListener('click', onClick, true)
		}
	}
}
