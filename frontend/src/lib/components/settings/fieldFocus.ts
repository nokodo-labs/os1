/**
 * reveal a settings field: scroll it into view, flash it, and focus its control.
 *
 * rendered fields register themselves through `settingsFieldAnchor`, so callers
 * address a field by id and never touch the DOM. a request for a field whose
 * section has not rendered yet is held until it registers, which is what lets a
 * search result navigate and reveal in one call.
 *
 * mirrors `lib/chat/messageFocus.ts`, the same contract for chat messages.
 */

import type { Attachment } from 'svelte/attachments'

const FLASH_MS = 900

/** how long a reveal waits for a section that is still rendering. */
export const FIELD_REVEAL_WAIT_MS = 2000

const FOCUSABLE =
	'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'

const anchors = new Map<string, HTMLElement>()

export interface RevealOptions {
	behavior?: ScrollBehavior
	block?: ScrollLogicalPosition
	/** ms to keep waiting for the field to mount. 0 = only if already there. */
	wait?: number
	/** move keyboard focus to the field's first control. */
	focus?: boolean
}

interface PendingReveal {
	id: string
	options: RevealOptions
	settle: (revealed: boolean) => void
	timer: ReturnType<typeof setTimeout>
}

// one target at a time: a newer request supersedes whatever was still waiting.
let pending: PendingReveal | null = null

function settlePending(revealed: boolean): void {
	if (!pending) return
	const current = pending
	pending = null
	clearTimeout(current.timer)
	current.settle(revealed)
}

/** drop a reveal that is still waiting, e.g. when the section changes. */
export function cancelSettingsFieldReveal(): void {
	settlePending(false)
}

/** in-flight flash per element, so revealing the same field twice restarts it. */
const flashes = new WeakMap<HTMLElement, Animation>()

function flash(node: HTMLElement): void {
	flashes.get(node)?.cancel()
	const tint = 'color-mix(in oklab, var(--color-accent) 26%, transparent)'
	const computed = getComputedStyle(node).borderRadius
	const radius = computed && computed !== '0px' ? computed : '1.25rem'
	const animation = node.animate(
		[
			{ backgroundColor: 'transparent', borderRadius: radius },
			{ backgroundColor: tint, borderRadius: radius, offset: 0.25 },
			{ backgroundColor: 'transparent', borderRadius: radius },
		],
		{ duration: FLASH_MS, easing: 'ease-out' }
	)
	flashes.set(node, animation)
}

function focusControl(node: HTMLElement): void {
	const control = node.querySelector(FOCUSABLE)
	if (control instanceof HTMLElement) control.focus({ preventScroll: true })
}

function reveal(node: HTMLElement, options: RevealOptions): void {
	node.scrollIntoView({
		block: options.block ?? 'center',
		behavior: options.behavior ?? 'smooth',
	})
	flash(node)
	if (options.focus !== false) focusControl(node)
}

function register(id: string, node: HTMLElement): void {
	anchors.set(id, node)
	node.dataset.settingsField = id
	if (pending?.id !== id) return
	const options = pending.options
	settlePending(true)
	// let the freshly mounted section lay out before measuring the scroll
	requestAnimationFrame(() => reveal(node, options))
}

function unregister(id: string, node: HTMLElement): void {
	if (anchors.get(id) === node) anchors.delete(id)
}

/**
 * scroll to a settings field and flash it.
 *
 * resolves false when the field never showed up within `wait`, which is the
 * caller's cue to leave the section scrolled where it landed.
 */
export function revealSettingsField(id: string, options: RevealOptions = {}): Promise<boolean> {
	settlePending(false)
	const node = anchors.get(id)
	if (node) {
		reveal(node, options)
		return Promise.resolve(true)
	}
	const wait = options.wait ?? 0
	if (wait <= 0) return Promise.resolve(false)
	return new Promise<boolean>((resolve) => {
		pending = {
			id,
			options,
			settle: resolve,
			timer: setTimeout(() => settlePending(false), wait),
		}
	})
}

/** mark an element as the scroll target for a settings field id. */
export function settingsFieldAnchor(id: string): Attachment<HTMLElement> {
	return (node) => {
		register(id, node)
		return () => {
			unregister(id, node)
		}
	}
}
