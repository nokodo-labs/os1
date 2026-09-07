/**
 * eat a click on its way in, for as long as the caller says to.
 *
 * a tap that only reveals a toolbar must not also press the button it landed
 * on. the guard listens in the capture phase, so the click dies before any
 * handler underneath sees it, and `when` decides one click at a time.
 */

import type { Attachment } from 'svelte/attachments'

export interface SwallowClickOptions {
	/** consulted on every click: true eats this one. */
	when: () => boolean
	/** a click was eaten - callers disarm whatever `when` reads. */
	onSwallow?: () => void
}

export function swallowclick(options: SwallowClickOptions): Attachment<HTMLElement> {
	return (node) => {
		function onClick(event: MouseEvent): void {
			if (!options.when()) return
			event.stopPropagation()
			event.preventDefault()
			options.onSwallow?.()
		}

		node.addEventListener('click', onClick, { capture: true })

		return () => {
			node.removeEventListener('click', onClick, { capture: true })
		}
	}
}
