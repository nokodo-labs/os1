/**
 * the verb library the think row walks while a thought runs (F144): it has to
 * be big, lowercase, and shuffled so the same word never lands twice in a row.
 */

import {
	createThinkingVerbCycle,
	THINKING_VERBS,
	thinkingVerbDelayMs,
	VERB_ROTATION_MAX_MS,
	VERB_ROTATION_MIN_MS,
} from '$lib/chat/thinkingVerbs'
import { describe, expect, it } from 'vitest'

/** a small deterministic prng so shuffling is testable without flake. */
function seeded(seed: number): () => number {
	let state = (seed * 1103515245 + 12345) >>> 0
	return () => {
		state = (state * 1103515245 + 12345) >>> 0
		return state / 0x100000000
	}
}

describe('the thinking verb library', () => {
	it('offers a large set of unique lowercase gerunds', () => {
		expect(THINKING_VERBS.length).toBeGreaterThanOrEqual(80)
		expect(new Set(THINKING_VERBS).size).toBe(THINKING_VERBS.length)
		for (const verb of THINKING_VERBS) {
			expect(verb).toBe(verb.toLowerCase())
			expect(verb.trim()).toBe(verb)
			expect(verb).toMatch(/ing\b/)
		}
	})

	it('holds each verb for three to five seconds', () => {
		expect(thinkingVerbDelayMs(() => 0)).toBe(VERB_ROTATION_MIN_MS)
		expect(thinkingVerbDelayMs(() => 1)).toBe(VERB_ROTATION_MAX_MS)
		const delay = thinkingVerbDelayMs(seeded(7))
		expect(delay).toBeGreaterThanOrEqual(VERB_ROTATION_MIN_MS)
		expect(delay).toBeLessThanOrEqual(VERB_ROTATION_MAX_MS)
	})
})

describe('the verb cycle', () => {
	it('spends the whole library before repeating a verb', () => {
		const cycle = createThinkingVerbCycle(seeded(42))
		const drawn = THINKING_VERBS.map(() => cycle.next())

		expect(new Set(drawn).size).toBe(THINKING_VERBS.length)
	})

	it('shuffles instead of walking the library in order', () => {
		const cycle = createThinkingVerbCycle(seeded(3))
		const drawn = THINKING_VERBS.map(() => cycle.next())

		expect(drawn).not.toEqual([...THINKING_VERBS])
		const differentSeed = createThinkingVerbCycle(seeded(9))
		expect(THINKING_VERBS.map(() => differentSeed.next())).not.toEqual(drawn)
	})

	it('never shows the same verb twice in a row, refill boundaries included', () => {
		const repeats: string[] = []
		for (let seed = 0; seed < 300; seed++) {
			const cycle = createThinkingVerbCycle(seeded(seed))
			let previous = cycle.next()
			for (let draw = 1; draw < THINKING_VERBS.length * 3; draw++) {
				const verb = cycle.next()
				if (verb === previous) repeats.push(verb)
				previous = verb
			}
		}

		expect(repeats).toEqual([])
	})
})
