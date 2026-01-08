import { on } from 'svelte/events'
export const useKeyDown = (opts) => {
	let listener
	const eventCallback = (event) => {
		if (opts.keys.includes(event.key)) {
			event.preventDefault()
			opts.callback()
		}
	}
	$effect(() => {
		if (opts.isActive && !listener) {
			listener = on(window, 'keydown', eventCallback)
		} else {
			listener?.()
			listener = null
		}
		return () => {
			listener?.()
			listener = null
		}
	})
}
