/**
 * dirty tracking for modal forms.
 *
 * one rule for every modal with a save button: the form is dirty when its
 * current values differ from the values the modal opened with. a modal seeds
 * its fields, calls `reset()` to snapshot them, and hands `dirty` to
 * `ModalSaveButton`, which stays inert until something actually changed.
 */

import { untrack } from 'svelte'

/** the values a modal form edits, keyed by field. */
export type FormValues = Record<string, unknown>

/** structural equality over form values; arrays compare in order. */
export function sameFormValues(a: unknown, b: unknown): boolean {
	if (a === b) return true
	if (Array.isArray(a) || Array.isArray(b)) {
		if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
		return a.every((item, index) => sameFormValues(item, b[index]))
	}
	if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false
	const entries: [string, unknown][] = Object.entries(a)
	const others: [string, unknown][] = Object.entries(b)
	if (entries.length !== others.length) return false
	return entries.every(([key, value]) => {
		const other = others.find(([otherKey]) => otherKey === key)
		return other !== undefined && sameFormValues(value, other[1])
	})
}

/** deep copy, so a snapshot never aliases the reactive values it was taken from. */
function cloneValue(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(cloneValue)
	if (value === null || typeof value !== 'object') return value
	const entries: [string, unknown][] = Object.entries(value)
	return Object.fromEntries(entries.map(([key, item]) => [key, cloneValue(item)]))
}

export class ModalFormDirty {
	#read: () => FormValues
	#baseline = $state.raw<FormValues | null>(null)

	constructor(read: () => FormValues) {
		this.#read = read
	}

	/** snapshot the values the modal opened with; call it right after seeding the fields. */
	reset(): void {
		const values = untrack(this.#read)
		this.#baseline = Object.fromEntries(
			Object.entries(values).map(([key, value]) => [key, cloneValue(value)])
		)
	}

	/** true once the form differs from what it opened with. */
	get dirty(): boolean {
		const baseline = this.#baseline
		return baseline !== null && !sameFormValues(this.#read(), baseline)
	}
}
