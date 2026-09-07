/**
 * press-and-hold gesture for touch and mouse.
 *
 * fires once the pointer has stayed down, without wandering, for `duration`
 * ms. a hold that fires swallows the click it would otherwise release into,
 * and the native context menu while a press is in progress. there is no
 * keyboard equivalent: callers must offer one.
 *
 * known limit: android chrome still recognises its own hold at ~500ms and
 * moves focus, which drops the virtual keyboard. cancelling touchstart or
 * pointerdown does not prevent it (tested), so do not rely on a hold while
 * a text field must stay focused.
 */

import { hapticFeedback } from '$lib/utils/haptics'
import type { Attachment } from 'svelte/attachments'

export interface LongPressOptions {
	onLongPress: (event: PointerEvent) => void
	/** hold time in ms before the gesture fires. */
	duration?: number
	/** pointer travel in px that cancels the hold. */
	moveTolerance?: number
	/**
	 * gate a press before it arms. a press that never arms keeps its click and
	 * the native context menu, so use this to let a descendant or a pointer type
	 * out of the gesture.
	 */
	shouldStart?: (event: PointerEvent) => boolean
	/** vibrate when the hold fires (subject to the user's haptics setting). */
	haptic?: boolean
	disabled?: boolean
}

const DEFAULT_DURATION_MS = 450
const DEFAULT_MOVE_TOLERANCE_PX = 10

export function longpress(options: LongPressOptions): Attachment<HTMLElement> {
	return (node) => {
		if (options.disabled) return
		let timer: ReturnType<typeof setTimeout> | null = null
		let pointerId: number | null = null
		let startX = 0
		let startY = 0
		let fired = false

		function clear(): void {
			if (timer !== null) {
				clearTimeout(timer)
				timer = null
			}
			pointerId = null
		}

		function onPointerDown(event: PointerEvent): void {
			if (event.button !== 0 || event.isPrimary === false) return
			if (options.shouldStart && !options.shouldStart(event)) return
			clear()
			fired = false
			pointerId = event.pointerId
			startX = event.clientX
			startY = event.clientY
			timer = setTimeout(() => {
				timer = null
				fired = true
				if (options.haptic !== false) hapticFeedback()
				options.onLongPress(event)
			}, options.duration ?? DEFAULT_DURATION_MS)
		}

		function onPointerMove(event: PointerEvent): void {
			if (pointerId === null || event.pointerId !== pointerId) return
			const tolerance = options.moveTolerance ?? DEFAULT_MOVE_TOLERANCE_PX
			if (
				Math.abs(event.clientX - startX) > tolerance ||
				Math.abs(event.clientY - startY) > tolerance
			) {
				clear()
			}
		}

		function onPointerEnd(event: PointerEvent): void {
			if (pointerId !== null && event.pointerId === pointerId) clear()
		}

		function onClick(event: MouseEvent): void {
			if (!fired) return
			fired = false
			event.preventDefault()
			event.stopImmediatePropagation()
		}

		function onContextMenu(event: MouseEvent): void {
			if (pointerId !== null || fired) event.preventDefault()
		}

		node.addEventListener('pointerdown', onPointerDown)
		node.addEventListener('pointermove', onPointerMove)
		node.addEventListener('pointerup', onPointerEnd)
		node.addEventListener('pointercancel', onPointerEnd)
		node.addEventListener('pointerleave', onPointerEnd)
		node.addEventListener('click', onClick, true)
		node.addEventListener('contextmenu', onContextMenu)

		return () => {
			clear()
			node.removeEventListener('pointerdown', onPointerDown)
			node.removeEventListener('pointermove', onPointerMove)
			node.removeEventListener('pointerup', onPointerEnd)
			node.removeEventListener('pointercancel', onPointerEnd)
			node.removeEventListener('pointerleave', onPointerEnd)
			node.removeEventListener('click', onClick, true)
			node.removeEventListener('contextmenu', onContextMenu)
		}
	}
}
