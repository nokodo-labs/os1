import { HOME_PLACEHOLDER_EXAMPLES, placeholderTexts } from '$lib/chat/placeholderExamples'
import { PlaceholderRotation, placeholderSwapTimings } from '$lib/chat/placeholderRotation.svelte'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const POOL = ['one', 'two', 'three', 'four', 'five']

let visibility: DocumentVisibilityState

function setVisibility(state: DocumentVisibilityState): void {
	visibility = state
	document.dispatchEvent(new Event('visibilitychange'))
}

/** reproducible stand-in for Math.random. */
function prng(seed: number): () => number {
	let state = seed
	return () => {
		state = (state * 1664525 + 1013904223) % 4294967296
		return state / 4294967296
	}
}

beforeEach(() => {
	vi.useFakeTimers()
	visibility = 'visible'
	Object.defineProperty(document, 'visibilityState', {
		configurable: true,
		get: () => visibility,
	})
})

afterEach(() => {
	vi.useRealTimers()
})

describe('PlaceholderRotation', () => {
	it('shows a line immediately and swaps once the dwell elapses', () => {
		const rotation = new PlaceholderRotation({ examples: POOL, random: () => 0 })
		rotation.start()

		const first = rotation.current
		expect(POOL).toContain(first)

		vi.advanceTimersByTime(3999)
		expect(rotation.current).toBe(first)

		vi.advanceTimersByTime(1)
		expect(rotation.current).not.toBe(first)

		rotation.stop()
	})

	it('keeps every dwell inside the 4-6s window', () => {
		const rotation = new PlaceholderRotation({ examples: POOL, random: prng(7) })
		rotation.start()

		let last = Date.now()
		for (let step = 0; step < 12; step++) {
			const before = rotation.current
			vi.advanceTimersToNextTimer()
			const elapsed = Date.now() - last
			last = Date.now()
			expect(elapsed).toBeGreaterThanOrEqual(4000)
			expect(elapsed).toBeLessThanOrEqual(6000)
			expect(rotation.current).not.toBe(before)
		}

		rotation.stop()
	})

	it('stops instantly mid-dwell and never swaps again', () => {
		const rotation = new PlaceholderRotation({ examples: POOL, random: () => 0 })
		rotation.start()

		vi.advanceTimersByTime(2000)
		const showing = rotation.current
		rotation.stop()

		vi.advanceTimersByTime(60_000)
		expect(rotation.current).toBe(showing)
		expect(vi.getTimerCount()).toBe(0)
		expect(rotation.isRunning).toBe(false)
	})

	it('exhausts the pool before reshuffling, with no repeat across the seam', () => {
		const rotation = new PlaceholderRotation({ examples: POOL, random: prng(42) })
		rotation.start()

		const seen: string[] = [rotation.current]
		for (let step = 0; step < POOL.length * 3 - 1; step++) {
			vi.advanceTimersToNextTimer()
			seen.push(rotation.current)
		}
		rotation.stop()

		for (let cycle = 0; cycle < 3; cycle++) {
			const chunk = seen.slice(cycle * POOL.length, (cycle + 1) * POOL.length)
			expect([...chunk].sort()).toEqual([...POOL].sort())
		}
		for (let i = 1; i < seen.length; i++) {
			expect(seen[i]).not.toBe(seen[i - 1])
		}
	})

	it('runs no timer while the tab is hidden and resumes when it returns', () => {
		const rotation = new PlaceholderRotation({ examples: POOL, random: () => 0 })
		rotation.start()
		const first = rotation.current

		setVisibility('hidden')
		expect(vi.getTimerCount()).toBe(0)

		vi.advanceTimersByTime(60_000)
		expect(rotation.current).toBe(first)

		setVisibility('visible')
		vi.advanceTimersByTime(4000)
		expect(rotation.current).not.toBe(first)

		rotation.stop()
	})

	it('schedules nothing when started on a hidden tab', () => {
		visibility = 'hidden'
		const rotation = new PlaceholderRotation({ examples: POOL, random: () => 0 })
		rotation.start()

		expect(rotation.current).not.toBe('')
		expect(vi.getTimerCount()).toBe(0)

		rotation.stop()
	})

	it('resumes on the line it left off on', () => {
		const rotation = new PlaceholderRotation({ examples: POOL, random: () => 0 })
		rotation.start()
		vi.advanceTimersByTime(4000)
		const showing = rotation.current
		rotation.stop()

		rotation.start()
		expect(rotation.current).toBe(showing)
		rotation.stop()
	})

	it('stays put with a single example and does nothing with none', () => {
		const single = new PlaceholderRotation({ examples: ['only one'], random: () => 0 })
		single.start()
		vi.advanceTimersByTime(60_000)
		expect(single.current).toBe('only one')
		expect(vi.getTimerCount()).toBe(0)
		single.stop()

		const empty = new PlaceholderRotation({ examples: [], random: () => 0 })
		empty.start()
		expect(empty.current).toBe('')
		expect(empty.isRunning).toBe(false)
	})
})

describe('placeholderSwapTimings', () => {
	it('collapses to an instant cut under reduced motion', () => {
		expect(placeholderSwapTimings(true)).toEqual({ outMs: 0, inMs: 0, inDelayMs: 0 })
	})

	it('rolls the lines when motion is allowed', () => {
		const timings = placeholderSwapTimings(false)
		expect(timings.outMs).toBeGreaterThan(0)
		expect(timings.inMs).toBeGreaterThan(0)
		expect(timings.inDelayMs).toBeGreaterThan(0)
	})
})

describe('placeholder library', () => {
	it('is huge, unique, and lowercase', () => {
		const texts = placeholderTexts()
		expect(texts.length).toBeGreaterThanOrEqual(60)
		expect(new Set(texts).size).toBe(texts.length)
		for (const text of texts) {
			expect(text[0]).toBe(text[0].toLowerCase())
			expect(text.trim()).toBe(text)
		}
	})

	it('narrows to the requested surfaces', () => {
		const notes = placeholderTexts(['notes'])
		expect(notes.length).toBeGreaterThan(0)
		expect(notes.length).toBeLessThan(HOME_PLACEHOLDER_EXAMPLES.length)
		for (const text of notes) {
			expect(HOME_PLACEHOLDER_EXAMPLES.find((e) => e.text === text)?.surface).toBe('notes')
		}
	})
})
