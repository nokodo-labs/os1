/** the verb library the think row cycles through while a thought is running. */

/** lowercase gerunds, straight and playful, shown one at a time on the think row. */
export const THINKING_VERBS: readonly string[] = [
	'thinking',
	'reasoning',
	'pondering',
	'deliberating',
	'mulling',
	'mulling it over',
	'ruminating',
	'reflecting',
	'contemplating',
	'considering',
	'weighing',
	'weighing options',
	'analyzing',
	'evaluating',
	'assessing',
	'examining',
	'exploring',
	'investigating',
	'planning',
	'mapping it out',
	'working it out',
	'figuring it out',
	'puzzling it out',
	'thinking it through',
	'reasoning it through',
	'sorting it out',
	'untangling',
	'unpacking',
	'breaking it down',
	'digging in',
	'digging deeper',
	'scanning',
	'cross-referencing',
	'double-checking',
	'verifying',
	'comparing notes',
	'prioritizing',
	'sequencing',
	'structuring',
	'outlining',
	'drafting',
	'sketching it out',
	'framing it',
	'reframing',
	'narrowing it down',
	'zooming out',
	'zooming in',
	'connecting dots',
	'following the thread',
	'tracing the logic',
	'testing assumptions',
	'questioning assumptions',
	'running the numbers',
	'doing the math',
	'forecasting',
	'second-guessing',
	'sanity-checking',
	'stress-testing',
	'poking holes',
	'filling in gaps',
	'gathering context',
	'recalling',
	'piecing it together',
	'lining things up',
	'tidying the logic',
	'refining',
	'polishing the plan',
	'converging',
	'settling on it',
	'chewing on it',
	'sitting with it',
	'letting it simmer',
	'letting it marinate',
	'brewing',
	'percolating',
	'stewing on it',
	'noodling',
	'tinkering',
	'cooking',
	'staring into space',
	'squinting at it',
	'scratching my head',
	'pacing around',
	'thinking out loud',
	'going down a rabbit hole',
	'spelunking',
	'going deep',
	'herding thoughts',
	'wrangling ideas',
	'shuffling ideas',
	'turning it over',
	'flipping it around',
	'taking another pass',
	'taking a second look',
	'trying another angle',
	'following a hunch',
	'having a think',
	'gathering my thoughts',
	'getting my bearings',
	'warming up',
]

/** shortest time a verb stays on screen. */
export const VERB_ROTATION_MIN_MS = 3000
/** longest time a verb stays on screen. */
export const VERB_ROTATION_MAX_MS = 5000

/** picks how long the next verb should hold before the row swaps it out. */
export function thinkingVerbDelayMs(random: () => number = Math.random): number {
	const span = VERB_ROTATION_MAX_MS - VERB_ROTATION_MIN_MS
	return VERB_ROTATION_MIN_MS + Math.round(random() * span)
}

export interface ThinkingVerbCycle {
	/** returns the next verb, never repeating until the whole library is spent. */
	next(): string
}

/** creates a shuffled, no-repeat walk over the verb library. */
export function createThinkingVerbCycle(random: () => number = Math.random): ThinkingVerbCycle {
	let bag: string[] = []
	let last: string | null = null

	function refill() {
		bag = shuffle(THINKING_VERBS, random)
		// the bag is drained from the end, so keep a reshuffle from repeating
		// the verb that is still on screen.
		if (bag.length > 1 && bag[bag.length - 1] === last) {
			const swapAt = bag.length - 2
			const tail = bag[bag.length - 1]
			bag[bag.length - 1] = bag[swapAt]
			bag[swapAt] = tail
		}
	}

	return {
		next() {
			if (bag.length === 0) refill()
			const verb = bag.pop() ?? THINKING_VERBS[0]
			last = verb
			return verb
		},
	}
}

function shuffle(source: readonly string[], random: () => number): string[] {
	const items = [...source]
	for (let i = items.length - 1; i > 0; i--) {
		const j = Math.min(i, Math.floor(random() * (i + 1)))
		const swap = items[i]
		items[i] = items[j]
		items[j] = swap
	}
	return items
}
