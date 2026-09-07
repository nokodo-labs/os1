/**
 * wheel handling that `onwheel` cannot express.
 *
 * svelte attaches its own listeners with the browser default, so a handler that
 * must not stall the scroller, or one that must `preventDefault`, has to say so
 * when it subscribes.
 */

import type { Attachment } from 'svelte/attachments'

/** wheel events that never block scrolling; the handler cannot preventDefault. */
export function passiveWheel(onWheel: (event: WheelEvent) => void): Attachment<HTMLElement> {
	return (node) => {
		node.addEventListener('wheel', onWheel, { passive: true })
		return () => {
			node.removeEventListener('wheel', onWheel)
		}
	}
}

/**
 * a vertical wheel scrolls the element sideways.
 *
 * for rows that only overflow horizontally: a mouse has no sideways wheel, so
 * without this the content past the edge is unreachable on the desktop.
 */
export function wheelToHScroll(): Attachment<HTMLElement> {
	return (node) => {
		function onWheel(event: WheelEvent): void {
			if (event.deltaY === 0) return
			event.preventDefault()
			node.scrollLeft += event.deltaY
		}

		node.addEventListener('wheel', onWheel, { passive: false })

		return () => {
			node.removeEventListener('wheel', onWheel)
		}
	}
}
