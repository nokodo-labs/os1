/**
 * shared placement math for floating menus.
 *
 * `PopupMenu` drops below its anchor and `SidePopupMenu` opens beside it, but
 * both have to stay inside the viewport - flip to the opposite side when the
 * preferred one has no room, and clamp when neither does (a submenu overlapping
 * its parent beats a submenu running off the screen).
 */

export interface MenuAnchorRect {
	top: number
	bottom: number
	left: number
	right: number
}

/** breathing room kept between a menu and the viewport edge. */
export const MENU_EDGE_MARGIN = 6

/** clamps a start offset so a `size`-long menu stays inside `viewport`. */
export function fitInside(start: number, size: number, viewport: number): number {
	const last = viewport - size - MENU_EDGE_MARGIN
	if (last <= MENU_EDGE_MARGIN) return MENU_EDGE_MARGIN
	return Math.min(Math.max(start, MENU_EDGE_MARGIN), last)
}

/** below the anchor, flipped above when it does not fit, clamped when neither side does. */
export function placeBelow(
	anchor: MenuAnchorRect,
	height: number,
	viewportHeight: number,
	gap: number
): number {
	const below = anchor.bottom + gap
	if (below + height + MENU_EDGE_MARGIN <= viewportHeight) return below
	const above = anchor.top - height - gap
	if (above >= MENU_EDGE_MARGIN) return above
	return fitInside(below, height, viewportHeight)
}

/** right of the anchor, flipped left when it does not fit, clamped when neither side does. */
export function placeBeside(
	anchor: MenuAnchorRect,
	width: number,
	viewportWidth: number,
	gap: number
): number {
	const right = anchor.right + gap
	if (right + width + MENU_EDGE_MARGIN <= viewportWidth) return right
	const left = anchor.left - width - gap
	if (left >= MENU_EDGE_MARGIN) return left
	return fitInside(right, width, viewportWidth)
}
