import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs))
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChild<T> = T extends { child?: any } ? Omit<T, 'child'> : T
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, 'children'> : T
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null }

// ────────────────────────────────────────────────────────────
// object utilities
// ────────────────────────────────────────────────────────────

export function isPlainObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
}

interface DeepMergeOptions {
	/** when true, null values from patch override target values. defaults to false. */
	applyNulls?: boolean
}

/**
 * recursively merge `patch` into `target`, returning a new object.
 * - `undefined` values in patch are always skipped.
 * - `null` values in patch are skipped unless `options.applyNulls` is true.
 * - nested plain objects are merged recursively.
 */
export function deepMerge<T extends Record<string, unknown>>(
	target: T,
	patch: Partial<T>,
	options?: DeepMergeOptions
): T {
	const applyNulls = options?.applyNulls ?? false
	const out = { ...target }

	for (const k in patch) {
		const patchVal = patch[k]
		if (patchVal === undefined) continue
		if (patchVal === null && !applyNulls) continue

		const targetVal = out[k]
		out[k] =
			isPlainObject(targetVal) && isPlainObject(patchVal)
				? (deepMerge(
						targetVal,
						patchVal as Partial<typeof targetVal>,
						options
					) as T[typeof k])
				: (patchVal as T[typeof k])
	}

	return out
}

// ────────────────────────────────────────────────────────────
// string utilities
// ────────────────────────────────────────────────────────────

/** extract up to 2 uppercase initials from a display name. */
export function getUserInitials(name: string): string {
	return name
		.split(' ')
		.map((n) => n[0])
		.join('')
		.toUpperCase()
		.slice(0, 2)
}

// ────────────────────────────────────────────────────────────
// function utilities
// ────────────────────────────────────────────────────────────

/** create a debounced version of `fn` that delays invocation by `delay` ms. */
export function debounce<A extends unknown[]>(
	fn: (...args: A) => void,
	delay: number
): (...args: A) => void {
	let timer: ReturnType<typeof setTimeout> | null = null
	return (...args: A) => {
		if (timer) clearTimeout(timer)
		timer = setTimeout(() => fn(...args), delay)
	}
}
