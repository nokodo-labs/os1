import { browser } from '$app/environment'

interface PortalOptions {
	target?: HTMLElement
}

export function portal(node: HTMLElement, options: PortalOptions = {}): { destroy(): void } {
	if (!browser) return { destroy() {} }

	const target = options.target ?? document.body
	target.appendChild(node)

	return {
		destroy() {
			if (node.parentNode) node.parentNode.removeChild(node)
		},
	}
}
