// the empty composer's rotating placeholder: which line is showing, for how
// long, and in what order.
//
// order is a shuffled queue rather than a random pick, so nothing repeats until
// the whole library has been seen. the timer only exists while the tab is
// visible - a backgrounded tab burns nothing.

import { onVisibilityChange } from '$lib/utils/frameLoop'

const DEFAULT_MIN_DWELL_MS = 4000
const DEFAULT_MAX_DWELL_MS = 6000

/** the swap: old line rolls up and out, new one springs in under it. */
const SWAP_OUT_MS = 180
const SWAP_IN_MS = 260
const SWAP_IN_DELAY_MS = 120

export interface PlaceholderSwapTimings {
	outMs: number
	inMs: number
	inDelayMs: number
}

/** reduced motion collapses the roll into a plain cut. */
export function placeholderSwapTimings(prefersReducedMotion: boolean): PlaceholderSwapTimings {
	if (prefersReducedMotion) return { outMs: 0, inMs: 0, inDelayMs: 0 }
	return { outMs: SWAP_OUT_MS, inMs: SWAP_IN_MS, inDelayMs: SWAP_IN_DELAY_MS }
}

export interface PlaceholderRotationOptions {
	examples: readonly string[]
	/** shortest dwell on one line. */
	minDwellMs?: number
	/** longest dwell on one line. */
	maxDwellMs?: number
	/** injectable for deterministic tests. */
	random?: () => number
}

function isDocumentHidden(): boolean {
	if (typeof document === 'undefined') return false
	return document.visibilityState === 'hidden'
}

export class PlaceholderRotation {
	/** the line currently on screen; empty until the first `start()`. */
	current = $state('')

	readonly #examples: readonly string[]
	readonly #minDwellMs: number
	readonly #maxDwellMs: number
	readonly #random: () => number

	#queue: string[] = []
	#timer: ReturnType<typeof setTimeout> | null = null
	#stopVisibility: (() => void) | null = null
	#running = false

	constructor(options: PlaceholderRotationOptions) {
		this.#examples = options.examples
		this.#minDwellMs = options.minDwellMs ?? DEFAULT_MIN_DWELL_MS
		this.#maxDwellMs = Math.max(options.maxDwellMs ?? DEFAULT_MAX_DWELL_MS, this.#minDwellMs)
		this.#random = options.random ?? Math.random
	}

	get isRunning(): boolean {
		return this.#running
	}

	/** start rotating, keeping whichever line is already on screen. */
	start = (): void => {
		if (this.#running) return
		if (this.#examples.length === 0) return
		this.#running = true
		if (this.current === '') this.current = this.#take()
		this.#stopVisibility = onVisibilityChange((visible) => {
			if (visible) this.#schedule()
			else this.#clearTimer()
		})
		this.#schedule()
	}

	/** stop instantly - mid-dwell, mid-animation, whenever. */
	stop = (): void => {
		this.#running = false
		this.#clearTimer()
		this.#stopVisibility?.()
		this.#stopVisibility = null
	}

	/** show the next line now and restart the dwell. */
	advance = (): void => {
		this.current = this.#take()
		this.#schedule()
	}

	#schedule = (): void => {
		this.#clearTimer()
		if (!this.#running) return
		// a single-example library has nowhere to go
		if (this.#examples.length < 2) return
		if (isDocumentHidden()) return
		this.#timer = setTimeout(() => {
			this.#timer = null
			this.advance()
		}, this.#dwellMs())
	}

	#clearTimer = (): void => {
		if (this.#timer === null) return
		clearTimeout(this.#timer)
		this.#timer = null
	}

	#dwellMs = (): number => {
		const span = this.#maxDwellMs - this.#minDwellMs
		return Math.round(this.#minDwellMs + this.#random() * span)
	}

	/** pull the next line, reshuffling the library once it runs dry. */
	#take = (): string => {
		if (this.#queue.length === 0) this.#refill()
		return this.#queue.pop() ?? this.current
	}

	#refill = (): void => {
		const shuffled = [...this.#examples]
		for (let i = shuffled.length - 1; i > 0; i--) {
			const j = Math.floor(this.#random() * (i + 1))
			;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
		}
		// the queue pops from the end, so a fresh shuffle whose last entry repeats
		// the line already showing would stutter across the seam
		const last = shuffled.length - 1
		if (shuffled.length > 1 && shuffled[last] === this.current) {
			;[shuffled[last], shuffled[0]] = [shuffled[0], shuffled[last]]
		}
		this.#queue = shuffled
	}
}
