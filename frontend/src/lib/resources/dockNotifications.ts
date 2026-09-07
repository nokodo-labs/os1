/**
 * the model behind the dock's notification list: how the run is cut into the
 * cards the list draws, which of its rows just arrived, and the motion a row
 * enters, opens and leaves on.
 *
 * one virtual item is one DAY, not one notification (F138). the ios
 * inset-grouped card the messages inbox uses (F98) needs a real element around
 * a run of rows to carry the frosted surface, and a recycled per-row cell can
 * never be one; a day-sized item can. it also keeps the virtual list honest:
 * a day is measured as a whole, so the run's total height stops being an
 * average of two very different row shapes.
 */

import { dayStamp } from '$lib/chat/chatTimestamps'
import type { Notification } from '$lib/stores/notifications.svelte'

/** where a row sits in its day's card, so it knows whether to draw a hairline. */
export type GroupPosition = 'single' | 'first' | 'middle' | 'last'

export type DockNotificationRow =
	| { kind: 'group'; id: string; label: string; notifications: Notification[] }
	| { kind: 'clear-all'; id: 'clear-all' }

export function groupPosition(index: number, total: number): GroupPosition {
	if (total <= 1) return 'single'
	if (index === 0) return 'first'
	if (index === total - 1) return 'last'
	return 'middle'
}

/**
 * day buckets in the order the store hands them over - that order is the order
 * the user reads in, so a day is closed as soon as another one starts rather
 * than re-opened later. clear-all closes the run: it is where the owner put it,
 * and the last item is reachable now that nothing between the items adds height
 * the list cannot measure.
 */
export function buildNotificationRows(
	list: readonly Notification[],
	now: Date = new Date()
): DockNotificationRow[] {
	if (list.length === 0) return []

	const rows: DockNotificationRow[] = []
	for (const notification of list) {
		const label = dayStamp(new Date(notification.created_at), now)
		const open = rows.at(-1)
		if (open?.kind === 'group' && open.label === label) open.notifications.push(notification)
		else
			rows.push({
				kind: 'group',
				id: `day-${notification.id}`,
				label,
				notifications: [notification],
			})
	}

	rows.push({ kind: 'clear-all', id: 'clear-all' })
	return rows
}

/**
 * a notification arriving while the dock is open drops in from above on the
 * app's flyup family (animations/entrance.svelte.ts): 270ms, back-loaded with a
 * little overshoot. the run is newest-first, so it lands at the TOP of it and
 * comes down rather than rising the way an outgoing bubble does.
 */
export const NOTIFICATION_ENTER_MS = 270
export const NOTIFICATION_ENTER_EASING = 'cubic-bezier(0.34, 1.56, 0.64, 1)'
export const NOTIFICATION_ENTER_KEYFRAMES: Keyframe[] = [
	{ opacity: 0, filter: 'blur(2px)', transform: 'translateY(-14px) scale(0.96)' },
	{ opacity: 1, filter: 'blur(0)', transform: 'translateY(0) scale(1)' },
]

/** dismissal flies to the edge first, on the 280ms the notification toasts leave in. */
export const NOTIFICATION_LEAVE_MS = 280

/**
 * opening and closing a row are the same move in reverse: the body's max-height
 * travels over 300ms on the standard ease-out. the clamp and the image are what
 * used to make the close look instant - they are held back until the height has
 * finished travelling, which is what this duration is for.
 */
export const NOTIFICATION_EXPAND_MS = 300

/**
 * which notifications actually ARRIVED, as opposed to already being there.
 *
 * deliberately not reactive: a cell consumes its claim from inside an
 * attachment, and a reactive set would make that consumption a dependency of
 * the very render that ran it.
 */
export class NotificationEntrance {
	#known = new Set<string>()
	#pending = new Set<string>()
	#seeded = false

	/** the batch already there on first load is the state of the world, not news. */
	seed(ids: readonly string[]): void {
		if (this.#seeded) return
		this.#seeded = true
		for (const id of ids) this.#known.add(id)
	}

	/** everything new since the seed earns one entrance. */
	track(ids: readonly string[]): void {
		if (!this.#seeded) return
		for (const id of ids) {
			if (this.#known.has(id)) continue
			this.#known.add(id)
			this.#pending.add(id)
		}
	}

	/** true once per newly-arrived id - a recycled cell finds nothing to play. */
	claim(id: string): boolean {
		return this.#pending.delete(id)
	}

	/**
	 * back to knowing nothing, for when the store empties (a logout clears it).
	 * without this the next account's whole inbox would read as arrivals.
	 */
	reset(): void {
		this.#known.clear()
		this.#pending.clear()
		this.#seeded = false
	}
}
