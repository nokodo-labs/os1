import { browser } from '$app/environment'
import type { Attachment } from 'svelte/attachments'

interface PortalOptions {
	target?: HTMLElement
}

/** move the element under `target` (default: body) for the life of the attachment. */
export function portal(options: PortalOptions = {}): Attachment<HTMLElement> {
	return (node) => {
		if (!browser) return
		const target = options.target ?? document.body
		target.appendChild(node)
		return () => {
			if (node.parentNode) node.parentNode.removeChild(node)
		}
	}
}
