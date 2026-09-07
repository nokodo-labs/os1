/**
 * where a lifted bubble and the actions around it are allowed to land.
 *
 * press-and-hold freezes the bubble's rect and draws its ensemble against it -
 * the time above, the action column beside, the menu below. a bubble held near
 * an edge, or one taller than the screen, would put half of that outside the
 * viewport, so imessage slides the whole thing inward as part of the lift.
 *
 * this is that arithmetic, kept free of the DOM: the cases that matter (a bubble
 * scrolled half off the top, one sitting on the composer, one taller than the
 * screen) are the ones hardest to stage in a browser and easiest to state here.
 */

export interface Box {
	left: number
	top: number
	width: number
	height: number
}

/** the part of the viewport the lift may cover: past the island, off the composer. */
export interface SafeArea {
	top: number
	bottom: number
	left: number
	right: number
}

export interface Offset {
	x: number
	y: number
}

/** what the lift paints around the frozen bubble rect. */
export interface LiftEnsemble {
	rect: Box
	/** how far the bubble grows about its own centre. */
	scale: number
	/** the time above the bubble, and the gap it keeps from it. 0 when there is none. */
	stampHeight: number
	stampGap: number
	/** the column of floating action bubbles, and the gap it keeps. */
	floatsWidth: number
	floatsHeight: number
	floatGap: number
	/** the side of the bubble the column hangs off. */
	align: 'left' | 'right'
}

/** everything the lift paints, as one box in viewport coordinates. */
export function liftEnsembleBox(ensemble: LiftEnsemble): Box {
	const { rect, align } = ensemble
	const growX = (rect.width * (ensemble.scale - 1)) / 2
	const growY = (rect.height * (ensemble.scale - 1)) / 2
	const centreY = rect.top + rect.height / 2
	const reach = ensemble.floatGap + ensemble.floatsWidth

	const top = Math.min(
		rect.top - growY - ensemble.stampGap - ensemble.stampHeight,
		centreY - ensemble.floatsHeight / 2
	)
	const bottom = Math.max(rect.top + rect.height + growY, centreY + ensemble.floatsHeight / 2)
	const left =
		align === 'right' ? Math.min(rect.left - growX, rect.left - reach) : rect.left - growX
	const right =
		align === 'left'
			? Math.max(rect.left + rect.width + growX, rect.left + rect.width + reach)
			: rect.left + rect.width + growX

	return { left, top, width: right - left, height: bottom - top }
}

/** how far `box` has to move to sit inside `safe`. */
export function fitTranslation(box: Box, safe: SafeArea): Offset {
	return {
		x: axisShift(box.left, box.width, safe.left, safe.right),
		y: axisShift(box.top, box.height, safe.top, safe.bottom),
	}
}

/**
 * a span too long for the room it has keeps its LEADING edge: the head of a
 * message taller than the screen is what the reader is holding, and the menu
 * takes whatever is left at the far end.
 */
function axisShift(start: number, size: number, min: number, max: number): number {
	if (size > max - min) return min - start
	if (start < min) return min - start
	if (start + size > max) return max - start - size
	return 0
}

/** slide a `size`-long span so it sits inside [min, max]; centred when it cannot. */
export function clampSpan(start: number, size: number, min: number, max: number): number {
	if (size > max - min) return min + (max - min - size) / 2
	return Math.min(Math.max(start, min), max - size)
}
