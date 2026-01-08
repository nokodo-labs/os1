import { on } from 'svelte/events'
import { SvelteSet } from 'svelte/reactivity'

export const useClickOutside = (props) => {
	const refs = new SvelteSet()
	let listener = null
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
		get attachment() {
			return props.isActive
				? (node) => {
						refs.add(node)
						if (!listener) {
							listener = on(node.ownerDocument, 'pointerdown', onClickOutside)
						}
						return () => {
							refs.delete(node)
							if (listener && refs.size === 0) {
								listener()
								listener = null
							}
						}
					}
				: null
		},
	}
}
