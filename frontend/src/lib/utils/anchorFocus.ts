/**
 * reveal an element addressed by id: scroll it into view and flash it.
 *
 * rendered items register themselves through the attachment, so callers name a
 * target and never touch the DOM. a request for something that has not mounted
 * yet is held until it registers, which is what lets a search anchor arrive
 * before the content it points at has finished loading.
 *
 * one instance per kind of anchor (messages, reminders, ...): ids only collide
 * inside an instance, and a pending reveal of one kind never cancels another.
 */

import type { Attachment } from 'svelte/attachments'

const DEFAULT_FLASH_MS = 650

/**
 * envelope (owner-tuned, F139): rise quickly, HOLD at full tint for a few
 * seconds, then remove quickly - the long lazy tail read as "barely visible".
 */
const FLASH_RISE = 0.06
const FLASH_HOLD_END = 0.88

export interface RevealOptions {
	behavior?: ScrollBehavior
	block?: ScrollLogicalPosition
	/** ms to keep waiting for the target to mount. 0 = only if already there. */
	wait?: number
}

export interface AnchorFocusOptions {
	/** corner radius the flash paints with, matched to the target's own. */
	radius?: string
	/** how long the flash lasts end to end, rise + hold + fade. */
	flashMs?: number
	/** run on registration, for anchors that also expose their id to the DOM. */
	mark?: (node: HTMLElement, id: string) => void
}

export interface AnchorFocus {
	/**
	 * mark an element as the scroll target for an id.
	 *
	 * a null id registers nothing, so markup shared with an item that has no
	 * persisted id yet can still carry the attachment. an id that changes
	 * re-registers the element: the attachment re-runs on the new id.
	 */
	anchor: (id: string | null) => Attachment<HTMLElement>
	/**
	 * scroll to a target and flash it.
	 *
	 * resolves false when the target never showed up within `wait`, which is the
	 * caller's cue to fall back.
	 */
	reveal: (id: string, options?: RevealOptions) => Promise<boolean>
	/** drop a reveal that is still waiting, e.g. when the container changes. */
	cancel: () => void
}

interface PendingReveal {
	id: string
	options: RevealOptions
	settle: (revealed: boolean) => void
	timer: ReturnType<typeof setTimeout>
}

export function createAnchorFocus(options: AnchorFocusOptions = {}): AnchorFocus {
	const radius = options.radius ?? '1.5rem'
	const flashMs = options.flashMs ?? DEFAULT_FLASH_MS
	const anchors = new Map<string, HTMLElement>()
	// in-flight flash per element, so revealing the same target twice restarts it
	const flashes = new WeakMap<HTMLElement, Animation>()
	// one target at a time: a newer request supersedes whatever was still waiting
	let pending: PendingReveal | null = null

	function settlePending(revealed: boolean): void {
		if (!pending) return
		const current = pending
		pending = null
		clearTimeout(current.timer)
		current.settle(revealed)
	}

	function flash(node: HTMLElement): void {
		flashes.get(node)?.cancel()
		const tint = 'color-mix(in oklab, var(--color-accent) 45%, transparent)'
		// rise, hold at full tint, then a long ease-out tail: the target has to be
		// findable after the scroll settles, not gone by the time the eye arrives.
		const animation = node.animate(
			[
				{
					backgroundColor: 'transparent',
					borderRadius: radius,
					offset: 0,
					easing: 'ease-out',
				},
				{
					backgroundColor: tint,
					borderRadius: radius,
					offset: FLASH_RISE,
					easing: 'linear',
				},
				{
					backgroundColor: tint,
					borderRadius: radius,
					offset: FLASH_HOLD_END,
					easing: 'ease-in-out',
				},
				{ backgroundColor: 'transparent', borderRadius: radius, offset: 1 },
			],
			{ duration: flashMs }
		)
		flashes.set(node, animation)
	}

	function reveal(node: HTMLElement, revealOptions: RevealOptions): void {
		node.scrollIntoView({
			block: revealOptions.block ?? 'center',
			behavior: revealOptions.behavior ?? 'auto',
		})
		flash(node)
	}

	function register(id: string | null, node: HTMLElement): void {
		if (!id) return
		anchors.set(id, node)
		options.mark?.(node, id)
		if (pending?.id !== id) return
		const revealOptions = pending.options
		settlePending(true)
		// let the freshly mounted subtree lay out before measuring the scroll
		requestAnimationFrame(() => reveal(node, revealOptions))
	}

	function unregister(id: string | null, node: HTMLElement): void {
		if (id && anchors.get(id) === node) anchors.delete(id)
	}

	return {
		anchor(id) {
			return (node) => {
				register(id, node)
				return () => {
					unregister(id, node)
				}
			}
		},
		reveal(id, revealOptions = {}) {
			settlePending(false)
			const node = anchors.get(id)
			if (node) {
				reveal(node, revealOptions)
				return Promise.resolve(true)
			}
			const wait = revealOptions.wait ?? 0
			if (wait <= 0) return Promise.resolve(false)
			return new Promise<boolean>((resolve) => {
				pending = {
					id,
					options: revealOptions,
					settle: resolve,
					timer: setTimeout(() => settlePending(false), wait),
				}
			})
		},
		cancel() {
			settlePending(false)
		},
	}
}
