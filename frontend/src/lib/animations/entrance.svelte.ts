// outgoing-bubble entrance: one home for all three modes (morph FLIP ghost,
// flyup WAAPI, none).  locally-originated bubbles (send, steering enqueue)
// use animateFrom() with a source rect; remotely-synced bubbles use the
// Svelte action which applies flyup on mount.
//
// usage:
//   const entrance = new EntranceController(() => mode)
//   <div bind:this={entrance.ghostEl}> ... </div>   // when entrance.ghost
//   await entrance.animateFrom(inputBoxEl, () => targetEl, text)
//   <div use:entrance.action> ... </div>            // remote sync entrance

import { tick } from 'svelte'

// ── constants ──────────────────────────────────────────────

export const FLIP_MS = 260
// near-still start, then a hard back-loaded ramp to a fast landing.
export const FLIP_EASING = 'cubic-bezier(0.7, 0, 0.84, 0.1)'

const FLYUP_MS = 270
const FLYUP_EASING = 'cubic-bezier(0.34, 1.56, 0.64, 1)'

const FLYUP_KEYFRAMES: Keyframe[] = [
	{
		opacity: 0,
		filter: 'blur(2px)',
		transform: 'translateY(34px) scale(0.92)',
	},
	{
		opacity: 1,
		filter: 'blur(0)',
		transform: 'translateY(0) scale(1)',
	},
]

// ── types ──────────────────────────────────────────────────

export type EntranceMode = 'morph' | 'flyup' | 'none'

export interface FlipGhost {
	text: string
	left: number
	top: number
	width: number
	height: number
}

// ── helpers ────────────────────────────────────────────────

function nextFrame(): Promise<void> {
	return new Promise((resolve) => {
		requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
	})
}

function flipKeyframes(
	first: DOMRect,
	last: DOMRect
): { left: string; top: string; width: string; height: string }[] {
	return [
		{
			left: `${first.left}px`,
			top: `${first.top}px`,
			width: `${first.width}px`,
			height: `${first.height}px`,
		},
		{
			left: `${last.left}px`,
			top: `${last.top}px`,
			width: `${last.width}px`,
			height: `${last.height}px`,
		},
	]
}

// ── controller ─────────────────────────────────────────────

export class EntranceController {
	ghost = $state<FlipGhost | null>(null)
	ghostEl = $state<HTMLElement | null>(null)
	inFlight = $state(false)

	#mode: () => EntranceMode
	#animating = false

	constructor(mode: () => EntranceMode) {
		this.#mode = mode
	}

	// ── public API ──────────────────────────────────────────

	/** entrance for a locally-originated bubble that has an input-box source
	 *  rect.  in morph mode this flies a ghost; in flyup mode it animates the
	 *  target in place; in none mode it returns immediately.
	 *
	 *  the target is resolved after a tick+frame so the caller can trigger
	 *  its render (set optimistic state / enqueue) between calling animateFrom
	 *  and the target being measured.  keep the target hidden (opacity:0)
	 *  during the flight; the ghost is revealed instead. */
	async animateFrom(
		source: HTMLElement | null,
		targetResolver: () => HTMLElement | null,
		text: string,
		onBeforeMeasure?: () => void
	): Promise<void> {
		const mode = this.#mode()
		if (mode === 'none') return

		this.#animating = true
		try {
			if (mode === 'morph' && source) {
				await this.#startMorph(source, targetResolver, text, onBeforeMeasure)
			} else {
				// flyup (or morph without source): apply right after tick (before
				// paint) so it never flashes at full opacity first.
				await tick()
				onBeforeMeasure?.()
				const target = targetResolver()
				if (target) {
					const anim = this.#applyFlyup(target)
					if (anim) await anim.finished
				}
			}
		} finally {
			this.#animating = false
		}
	}

	/** Svelte action: applies flyup entrance on mount for remotely-synced
	 *  steering rows.  skips when animateFrom is already handling the entrance
	 *  for this bubble (checked via #animating flag). */
	readonly action = (node: HTMLElement): void => {
		if (this.#animating) return
		if (this.#mode() === 'none') return
		this.#applyFlyup(node)
	}

	/** fallback flyup entrance for a remotely-synced bubble (e.g. a user
	 *  message sent from another session).  unlike `action`, this has no
	 *  #animating guard — the caller is expected to gate it (mark-and-consume)
	 *  so it fires exactly once for genuinely-new bubbles. */
	reveal(node: HTMLElement): void {
		if (this.#mode() === 'none') return
		this.#applyFlyup(node)
	}

	/** the outgoing bubble lands below the fold (user scrolled up): fly the ghost
	 *  down and out of the viewport to signal the message went down there. */
	async flyOutDown(source: HTMLElement | null, text: string): Promise<void> {
		if (this.#mode() === 'none' || !source) return
		const first = source.getBoundingClientRect()
		this.#animating = true
		this.inFlight = true
		this.ghost = {
			text,
			left: first.left,
			top: first.top,
			width: first.width,
			height: first.height,
		}
		try {
			await tick()
			const el = this.ghostEl
			if (!el || typeof el.animate !== 'function') return
			const anim = el.animate(
				[
					{ top: `${first.top}px`, opacity: 1 },
					{ top: `${window.innerHeight + first.height}px`, opacity: 0 },
				],
				{ duration: FLIP_MS, easing: FLIP_EASING, fill: 'forwards' }
			)
			await anim.finished.catch(() => {})
		} finally {
			this.inFlight = false
			await tick()
			this.ghost = null
			this.#animating = false
		}
	}

	reset(): void {
		this.inFlight = false
		this.ghost = null
	}

	// ── internals ───────────────────────────────────────────

	async #startMorph(
		source: HTMLElement,
		targetResolver: () => HTMLElement | null,
		text: string,
		onBeforeMeasure?: () => void
	): Promise<void> {
		const first = source.getBoundingClientRect()

		this.inFlight = true
		await tick()
		// bubble now occupies layout space (hidden via inFlight); make room
		// (scroll it into its final slot) before measuring the target rect.
		onBeforeMeasure?.()
		await nextFrame()

		const target = targetResolver()
		if (!target || typeof target.animate !== 'function') {
			this.inFlight = false
			return
		}
		const last = target.getBoundingClientRect()
		this.ghost = {
			text,
			left: first.left,
			top: first.top,
			width: first.width,
			height: first.height,
		}
		await tick()
		const el = this.ghostEl
		if (!el) {
			this.inFlight = false
			this.ghost = null
			return
		}

		const anim = el.animate(flipKeyframes(first, last), {
			duration: FLIP_MS,
			easing: FLIP_EASING,
			fill: 'forwards',
		})
		await anim.finished.catch(() => {})
		this.inFlight = false
		await tick()
		this.ghost = null
	}

	#applyFlyup(el: HTMLElement): Animation | null {
		if (typeof el.animate !== 'function') return null
		return el.animate(FLYUP_KEYFRAMES, {
			duration: FLYUP_MS,
			easing: FLYUP_EASING,
			fill: 'forwards',
		})
	}
}
