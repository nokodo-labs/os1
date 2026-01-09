import { on } from 'svelte/events'

/**
 * @param {{ keys: string[], isActive: boolean, callback: () => void }} opts
 */
export const useKeyDown = (opts) => {
	/** @type {(() => void) | null} */
	let listener = null
	/** @param {KeyboardEvent} event */
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
