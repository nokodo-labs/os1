/**
 * tell a scroll the user drove from one the app drove.
 *
 * a `scroll` listener cannot: `scrollTo` fires it exactly like a finger does.
 * the input events can, so wheel and touch travel are reported here and a
 * caller's pin stays authoritative while something else keeps scrolling.
 */

import type { Attachment } from 'svelte/attachments'

export type ScrollGestureDirection = 'up' | 'down' | 'unknown'

/**
 * notified whenever the user works the scroller themselves.
 *
 * touch travel is reported as `unknown`: a touchmove says nothing about which
 * way the content ended up going.
 */
export function scrollGesture(
	onGesture: (direction: ScrollGestureDirection) => void
): Attachment<HTMLElement> {
	return (node) => {
		function onWheel(event: WheelEvent): void {
			onGesture(event.deltaY < 0 ? 'up' : 'down')
		}

		function onTouchMove(): void {
			onGesture('unknown')
		}

		node.addEventListener('wheel', onWheel, { passive: true })
		node.addEventListener('touchmove', onTouchMove, { passive: true })

		return () => {
			node.removeEventListener('wheel', onWheel)
			node.removeEventListener('touchmove', onTouchMove)
		}
	}
}
