import { on } from 'svelte/events'
import { SvelteSet } from 'svelte/reactivity'

/**
 * @param {{ isActive: boolean, callback: () => void }} props
 */
export const useClickOutside = (props) => {
	const refs = new SvelteSet()
	/** @type {(() => void) | null} */
	let listener = null
	/** @param {PointerEvent} e */
	const onClickOutside = (e) => {
		let inRef = false
		if (props.isActive) {
			const path = e.composedPath()
			path.forEach((node) => {
				refs.forEach((ref) => {
					if (ref instanceof Node && node instanceof Node && ref?.isSameNode(node)) {
						inRef = true
					}
				})
			})
			if (!inRef) {
				props.callback()
			}
		}
	}
	return {
		/** @param {HTMLElement} node */
		attachment(node) {
			refs.add(node)
			if (!listener) {
				listener = on(node.ownerDocument, 'pointerdown', onClickOutside)
			}
			return {
				destroy: () => {
					refs.delete(node)
					if (listener && refs.size === 0) {
						listener()
						listener = null
					}
				},
			}
		},
	}
}
