/**
 * the dock's notification list model: the run cut into one virtual item per
 * day - the element that carries that day's frosted card - closed by the
 * clear-all row, plus the one-shot entrance a newly-arrived notification earns.
 */

import type { components } from '$lib/api/types'
import {
	buildNotificationRows,
	groupPosition,
	NotificationEntrance,
} from '$lib/resources/dockNotifications'
import { describe, expect, it } from 'vitest'

type Notification = components['schemas']['Notification']

const NOW = new Date('2026-09-03T15:00:00Z')

function notification(id: string, createdAt: string): Notification {
	return {
		id,
		user_id: 'user_me',
		event_id: `evt_${id}`,
		created_at: createdAt,
		read_at: null,
		dismissed: false,
	} as Notification
}

function iso(daysAgo: number, hour = 12): string {
	const date = new Date(NOW)
	date.setDate(date.getDate() - daysAgo)
	date.setHours(hour, 0, 0, 0)
	return date.toISOString()
}

describe('groupPosition', () => {
	it('gives a lone row every corner and a run its two ends', () => {
		expect(groupPosition(0, 1)).toBe('single')
		expect(groupPosition(0, 3)).toBe('first')
		expect(groupPosition(1, 3)).toBe('middle')
		expect(groupPosition(2, 3)).toBe('last')
	})

	it('never leaves a two-row card without both ends', () => {
		expect(groupPosition(0, 2)).toBe('first')
		expect(groupPosition(1, 2)).toBe('last')
	})
})

describe('buildNotificationRows', () => {
	it('draws nothing for an empty list', () => {
		expect(buildNotificationRows([], NOW)).toEqual([])
	})

	it('heads each day with its own quiet stamp', () => {
		const rows = buildNotificationRows(
			[notification('a', iso(0)), notification('b', iso(0, 9)), notification('c', iso(1))],
			NOW
		)

		expect(rows.filter((row) => row.kind === 'group').map((row) => row.label)).toEqual([
			'today',
			'yesterday',
		])
	})

	it('gives a day one item, so its card can be one element', () => {
		const rows = buildNotificationRows(
			[
				notification('a', iso(0)),
				notification('b', iso(0, 9)),
				notification('c', iso(0, 8)),
				notification('d', iso(1)),
			],
			NOW
		)

		expect(
			rows
				.filter((row) => row.kind === 'group')
				.map((row) => row.notifications.map((notif) => notif.id))
		).toEqual([['a', 'b', 'c'], ['d']])
	})

	it('keeps the order the store handed over', () => {
		const list = [
			notification('a', iso(0)),
			notification('b', iso(2)),
			notification('c', iso(9)),
		]
		const rows = buildNotificationRows(list, NOW)

		expect(
			rows.flatMap((row) =>
				row.kind === 'group' ? row.notifications.map((notif) => notif.id) : []
			)
		).toEqual(['a', 'b', 'c'])
	})

	it('gives every row a unique key the list can track', () => {
		const rows = buildNotificationRows(
			[notification('a', iso(0)), notification('b', iso(1)), notification('c', iso(1))],
			NOW
		)

		expect(new Set(rows.map((row) => row.id)).size).toBe(rows.length)
	})

	it('closes the run with clear-all, where the owner put it', () => {
		const rows = buildNotificationRows(
			[notification('a', iso(0)), notification('b', iso(1))],
			NOW
		)

		expect(rows.map((row) => row.kind)).toEqual(['group', 'group', 'clear-all'])
		expect(rows.at(-1)?.id).toBe('clear-all')
	})
})

describe('NotificationEntrance', () => {
	it('treats the first batch as the state of the world, not arrivals', () => {
		const entrance = new NotificationEntrance()

		entrance.seed(['a', 'b'])
		entrance.track(['a', 'b'])

		expect(entrance.claim('a')).toBe(false)
		expect(entrance.claim('b')).toBe(false)
	})

	it('gives a notification that arrives later exactly one entrance', () => {
		const entrance = new NotificationEntrance()
		entrance.seed(['a'])
		entrance.track(['a'])

		entrance.track(['new', 'a'])

		expect(entrance.claim('new')).toBe(true)
		expect(entrance.claim('new')).toBe(false)
	})

	it('never replays one for a cell that becomes another row', () => {
		const entrance = new NotificationEntrance()
		entrance.seed([])
		entrance.track(['a', 'b'])
		expect(entrance.claim('a')).toBe(true)

		// the same cell, scrolled onto an older row it has never claimed
		expect(entrance.claim('older')).toBe(false)
		expect(entrance.claim('a')).toBe(false)
	})

	it('re-seeds after the store empties, so the next inbox is not all arrivals', () => {
		const entrance = new NotificationEntrance()
		entrance.seed(['a'])
		entrance.track(['a'])

		entrance.reset()
		entrance.seed(['x', 'y'])
		entrance.track(['x', 'y'])

		expect(entrance.claim('x')).toBe(false)
		expect(entrance.claim('y')).toBe(false)
	})

	it('tracks nothing before the list has ever loaded', () => {
		const entrance = new NotificationEntrance()

		entrance.track(['a'])

		expect(entrance.claim('a')).toBe(false)
	})
})
