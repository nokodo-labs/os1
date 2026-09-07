/**
 * row context menu gesture: desktop right-click and touch hold open the one
 * menu the row already has behind its 3-dot trigger.
 *
 * applied to a row, it calls `onOpen` once per gesture with the viewport
 * coordinates the menu should open at: the pointer for a right-click (the
 * native menu is suppressed), the row's own bottom edge for a hold, since a
 * finger covers the point it pressed. holds are touch/pen only - a mouse has
 * the right button, and arming on a slow left click would swallow it.
 *
 * what it skips: a press or right-click that lands in text entry inside the
 * row (input, textarea, select, contenteditable) is left alone, so the native
 * editing menu and the caret keep working. links and buttons are NOT skipped:
 * rows here are built out of them, and the row menu is the superset action.
 * a descendant with its own gesture opts out by stopping `pointerdown`.
 */

import { longpress } from '$lib/attachments/longpress'
import type { Attachment } from 'svelte/attachments'

export type ContextMenuSource = 'pointer' | 'hold'

export interface ContextMenuAnchor {
	/** viewport x to open the menu at. */
	x: number
	/** viewport y to open the menu at. */
	y: number
	source: ContextMenuSource
}

export interface ContextMenuOptions {
	onOpen: (anchor: ContextMenuAnchor) => void
	/** hold time in ms before the touch gesture fires. */
	holdDuration?: number
	disabled?: boolean
}

const TEXT_ENTRY_SELECTOR = 'input, textarea, select'

function isTextEntry(node: HTMLElement, target: EventTarget | null): boolean {
	if (!(target instanceof Element)) return false
	if (target instanceof HTMLElement && target.isContentEditable) return true
	const field = target.closest(TEXT_ENTRY_SELECTOR)
	return field !== null && field !== node && node.contains(field)
}

export function contextmenu(options: ContextMenuOptions): Attachment<HTMLElement> {
	return (node) => {
		if (options.disabled) return
		let pressing = false
		let held = false

		const releaseHold = longpress({
			duration: options.holdDuration,
			shouldStart: (event) =>
				event.pointerType !== 'mouse' && !isTextEntry(node, event.target),
			onLongPress: () => {
				held = true
				const rect = node.getBoundingClientRect()
				options.onOpen({
					x: rect.left < window.innerWidth / 2 ? rect.left : rect.right,
					y: rect.bottom,
					source: 'hold',
				})
			},
		})(node)

		function onPointerDown(event: PointerEvent): void {
			if (event.button !== 0 || event.isPrimary === false) return
			pressing = true
			held = false
		}

		function onPointerEnd(): void {
			pressing = false
		}

		function onContextMenu(event: MouseEvent): void {
			// the hold owns this gesture, and longpress suppresses the native menu
			if (pressing || held) {
				held = false
				return
			}
			if (isTextEntry(node, event.target)) return
			event.preventDefault()
			options.onOpen({ x: event.clientX, y: event.clientY, source: 'pointer' })
		}

		node.addEventListener('pointerdown', onPointerDown)
		node.addEventListener('pointerup', onPointerEnd)
		node.addEventListener('pointercancel', onPointerEnd)
		node.addEventListener('pointerleave', onPointerEnd)
		node.addEventListener('contextmenu', onContextMenu)

		return () => {
			releaseHold?.()
			node.removeEventListener('pointerdown', onPointerDown)
			node.removeEventListener('pointerup', onPointerEnd)
			node.removeEventListener('pointercancel', onPointerEnd)
			node.removeEventListener('pointerleave', onPointerEnd)
			node.removeEventListener('contextmenu', onContextMenu)
		}
	}
}
