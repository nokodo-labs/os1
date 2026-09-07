// outgoing-bubble entrance animations (morph FLIP ghost, flyup, none).
// locally-originated bubbles call animateFrom()/morphTo() with a source rect;
// remotely-synced bubbles use the `attach` attachment (flyup on mount).

import { tick } from 'svelte'
import type { Attachment } from 'svelte/attachments'

export const FLIP_MS = 260
// back-loaded curve shared by the WAAPI morph (as a string) and the rAF
// tracking morph (sampled via flipEase below), so both feel identical.
const FLIP_CURVE = [0.7, 0, 0.84, 0.1] as const
export const FLIP_EASING = `cubic-bezier(${FLIP_CURVE.join(', ')})`

// per-second exp rate the tracking morph uses to chase a target that moves
// mid-flight; higher = snappier catch-up.
const TRACK_SMOOTHING = 18
// ceiling on post-timeline settling so the chase can't loop forever when the
// target never stops moving.
const SETTLE_MAX_MS = 600

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

export type EntranceMode = 'morph' | 'flyup' | 'none'

export interface FlipGhost {
	text: string
	left: number
	top: number
	width: number
	height: number
}

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

function rectOf(source: HTMLElement | DOMRect): DOMRect {
	return source instanceof HTMLElement ? source.getBoundingClientRect() : source
}

// sample a CSS cubic-bezier as y(x) via Newton-Raphson on x, so the rAF morph
// can match the WAAPI easing curve exactly.  x is normalized time in [0, 1].
function cubicBezierEasing(x1: number, y1: number, x2: number, y2: number): (x: number) => number {
	const cx = 3 * x1
	const bx = 3 * (x2 - x1) - cx
	const ax = 1 - cx - bx
	const cy = 3 * y1
	const by = 3 * (y2 - y1) - cy
	const ay = 1 - cy - by
	const sampleX = (t: number): number => ((ax * t + bx) * t + cx) * t
	const sampleY = (t: number): number => ((ay * t + by) * t + cy) * t
	const sampleDX = (t: number): number => (3 * ax * t + 2 * bx) * t + cx
	return (x: number): number => {
		if (x <= 0) return 0
		if (x >= 1) return 1
		let t = x
		for (let i = 0; i < 8; i++) {
			const dx = sampleX(t) - x
			if (Math.abs(dx) < 1e-4) break
			const slope = sampleDX(t)
			if (Math.abs(slope) < 1e-6) break
			t -= dx / slope
		}
		return sampleY(t)
	}
}

const flipEase = cubicBezierEasing(...FLIP_CURVE)

// ghost bubble's horizontal text inset; must match its template `px-3`.
const GHOST_INSET_X = 12

/** morph source rect for the chat input: horizontal extent from the textarea
 *  (where the text sits), vertical from the pill (so the ghost starts as tall as
 *  the input, not a short textarea-height bubble).  left is nudged by the
 *  textarea/ghost padding delta so the text doesn't jump on the first frame. */
export function inputBoxMorphSource(box: HTMLElement | null): HTMLElement | DOMRect | null {
	if (!box) return null
	const textarea = box.querySelector<HTMLTextAreaElement>('textarea')
	const pill = box.querySelector<HTMLElement>('[data-chat-input]') ?? box
	if (!textarea) return pill
	const ta = textarea.getBoundingClientRect()
	const p = pill.getBoundingClientRect()
	const taPadLeft = parseFloat(getComputedStyle(textarea).paddingLeft) || 0
	const left = ta.left + taPadLeft - GHOST_INSET_X
	return new DOMRect(left, p.top, ta.width, p.height)
}

export class EntranceController {
	ghost = $state<FlipGhost | null>(null)
	ghostEl = $state<HTMLElement | null>(null)
	inFlight = $state(false)

	#mode: () => EntranceMode
	#durationScale: () => number
	#animating = false

	constructor(mode: () => EntranceMode, durationScale?: () => number) {
		this.#mode = mode
		this.#durationScale = durationScale ?? (() => 1)
	}

	// effective durations; the debug duration knob scales them for slow-mo.
	get #flipMs(): number {
		return FLIP_MS * this.#durationScale()
	}
	get #flyupMs(): number {
		return FLYUP_MS * this.#durationScale()
	}

	/** entrance for a locally-originated bubble with an input-box source rect:
	 *  morph flies a ghost, flyup animates the target in place, none is a no-op.
	 *  the target is resolved after a tick+frame so the caller can render it
	 *  (set optimistic state) in between; keep it hidden (opacity:0) during the
	 *  flight while the ghost stands in. */
	async animateFrom(
		source: HTMLElement | DOMRect | null,
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
				// flyup (or morph w/o source): apply after tick (pre-paint) so it
				// never flashes at full opacity first.
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

	/** like animateFrom's morph, but geometry is rAF-driven and re-measures the
	 *  target each frame, so the ghost follows a target that moves mid-flight
	 *  (persist inserts the assistant placeholder -> thread scrolls).  a static
	 *  target reproduces the bake-once curve; non-morph modes delegate. */
	async morphTo(
		source: HTMLElement | DOMRect | null,
		targetResolver: () => HTMLElement | null,
		text: string,
		onBeforeMeasure?: () => void
	): Promise<void> {
		const mode = this.#mode()
		if (mode === 'none' || !source) return
		if (mode !== 'morph') {
			await this.animateFrom(source, targetResolver, text, onBeforeMeasure)
			return
		}
		this.#animating = true
		try {
			await this.#startMorphTracking(source, targetResolver, text, onBeforeMeasure)
		} finally {
			this.#animating = false
		}
	}

	/** attachment: flyup entrance on mount for remotely-synced steering rows;
	 *  skips when animateFrom is already animating this bubble. */
	readonly attach: Attachment<HTMLElement> = (node): void => {
		if (this.#animating) return
		if (this.#mode() === 'none') return
		this.#applyFlyup(node)
	}

	/** flyup entrance for a remotely-synced bubble, with no #animating guard:
	 *  the caller must gate it (mark-and-consume) so it fires once per new bubble. */
	reveal(node: HTMLElement): void {
		if (this.#mode() === 'none') return
		this.#applyFlyup(node)
	}

	/** the outgoing bubble lands below the fold (user scrolled up): fly the ghost
	 *  down and out of the viewport to signal the message went down there. */
	async flyOutDown(source: HTMLElement | DOMRect | null, text: string): Promise<void> {
		if (this.#mode() === 'none' || !source) return
		const first = rectOf(source)
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
				{ duration: this.#flipMs, easing: FLIP_EASING, fill: 'forwards' }
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

	async #startMorph(
		source: HTMLElement | DOMRect,
		targetResolver: () => HTMLElement | null,
		text: string,
		onBeforeMeasure?: () => void
	): Promise<void> {
		const first = rectOf(source)

		this.inFlight = true
		await tick()
		// make room (scroll into the final slot) before measuring the target.
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

		const fly = el.animate(flipKeyframes(first, last), {
			duration: this.#flipMs,
			easing: FLIP_EASING,
			fill: 'forwards',
		})
		this.#animateTint(el)
		await fly.finished.catch(() => {})
		this.inFlight = false
		await tick()
		this.ghost = null
	}

	// like #startMorph but geometry is rAF-driven (#runFlipChase) so it can
	// re-target a bubble that moves mid-flight.
	async #startMorphTracking(
		source: HTMLElement | DOMRect,
		targetResolver: () => HTMLElement | null,
		text: string,
		onBeforeMeasure?: () => void
	): Promise<void> {
		const first = rectOf(source)

		this.inFlight = true
		await tick()
		onBeforeMeasure?.()
		await nextFrame()

		const initial = targetResolver()
		if (!initial) {
			this.inFlight = false
			return
		}
		const initialRect = initial.getBoundingClientRect()
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

		this.#animateTint(el)
		await this.#runFlipChase(el, first, targetResolver, initialRect)
		this.inFlight = false
		await tick()
		this.ghost = null
	}

	/** drive left/top/width/height each frame: ease start -> target along the
	 *  FLIP curve, but chase an exp-smoothed target so a mid-flight move is
	 *  followed with no pop.  writes styles directly (no per-frame reactivity). */
	#runFlipChase(
		el: HTMLElement,
		from: DOMRect,
		targetResolver: () => HTMLElement | null,
		initialTarget: DOMRect
	): Promise<void> {
		return new Promise((resolve) => {
			const duration = this.#flipMs
			const startTime = performance.now()
			// seed the smoothed target with the first measured rect so a static target
			// has zero smoothing lag (identical to the bake-once curve).
			let toL = initialTarget.left
			let toT = initialTarget.top
			let toW = initialTarget.width
			let toH = initialTarget.height
			let prev = startTime

			const step = (now: number): void => {
				// clamp dt so a backgrounded tab (huge gap) doesn't teleport the chase.
				const dt = Math.min(0.05, (now - prev) / 1000)
				prev = now

				let residual = 0
				const targetEl = targetResolver()
				if (targetEl) {
					const r = targetEl.getBoundingClientRect()
					residual = Math.max(
						Math.abs(r.left - toL),
						Math.abs(r.top - toT),
						Math.abs(r.width - toW),
						Math.abs(r.height - toH)
					)
					const a = 1 - Math.exp(-TRACK_SMOOTHING * dt)
					toL += (r.left - toL) * a
					toT += (r.top - toT) * a
					toW += (r.width - toW) * a
					toH += (r.height - toH) * a
				}

				const p = duration > 0 ? Math.min(1, (now - startTime) / duration) : 1
				const e = flipEase(p)
				el.style.left = `${from.left + (toL - from.left) * e}px`
				el.style.top = `${from.top + (toT - from.top) * e}px`
				el.style.width = `${from.width + (toW - from.width) * e}px`
				el.style.height = `${from.height + (toH - from.height) * e}px`

				// done when the timeline completes AND the chase has caught the target,
				// or the settle cap elapses (target never stops) so we can't loop forever.
				if (p >= 1 && (residual < 0.5 || now - startTime - duration > SETTLE_MAX_MS)) {
					resolve()
					return
				}
				requestAnimationFrame(step)
			}
			requestAnimationFrame(step)
		})
	}

	/** fade the ghost's fill + glow from transparent to the accent color, read
	 *  from live theme vars so the landed state matches the real bubble.  shares
	 *  the FLIP timing + easing so color and shape morph in lockstep. */
	#animateTint(el: HTMLElement): Animation | null {
		if (typeof el.animate !== 'function') return null
		const cs = getComputedStyle(el)
		const rgb = cs.getPropertyValue('--accent-rgb').trim()
		const primary = cs.getPropertyValue('--accent-primary').trim()
		const border = cs.getPropertyValue('--accent-border').trim()
		if (!rgb || !primary || !border) return null
		return el.animate(
			[
				{
					backgroundColor: `rgb(${rgb} / 0)`,
					boxShadow: `0 4px 16px rgb(${rgb} / 0)`,
				},
				{ backgroundColor: primary, boxShadow: `0 4px 16px ${border}` },
			],
			{ duration: this.#flipMs, easing: FLIP_EASING, fill: 'both' }
		)
	}

	#applyFlyup(el: HTMLElement): Animation | null {
		if (typeof el.animate !== 'function') return null
		return el.animate(FLYUP_KEYFRAMES, {
			duration: this.#flyupMs,
			easing: FLYUP_EASING,
			fill: 'forwards',
		})
	}
}
