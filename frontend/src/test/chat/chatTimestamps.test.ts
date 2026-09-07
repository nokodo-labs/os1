/**
 * the transcript's own clock (F120/F127): when a silence earns a header, how
 * the moment is worded at each age, and when a receipt names a time at all.
 *
 * the time half is compared against `clockTime` rather than a literal, so the
 * suite says nothing about the runner's locale or hour cycle.
 */

import {
	clockTime,
	dayStamp,
	formatTimeHeader,
	needsTimeHeader,
	receiptStamp,
	RECEIPT_STAMP_GAP_MS,
	timeHeaderSegments,
	TIME_HEADER_GAP_MS,
} from '$lib/chat/chatTimestamps'
import { describe, expect, it } from 'vitest'

/** a fixed "now" on a wednesday afternoon, in local time. */
const NOW = new Date(2026, 8, 2, 15, 30)

function at(dayOffset: number, hour = 12, minute = 5): Date {
	return new Date(2026, 8, 2 - dayOffset, hour, minute)
}

describe('dayStamp', () => {
	it('names today and yesterday', () => {
		expect(dayStamp(at(0), NOW)).toBe('today')
		expect(dayStamp(at(1), NOW)).toBe('yesterday')
	})

	it('names the weekday while it is still unambiguous', () => {
		expect(dayStamp(at(2), NOW)).toBe('monday')
		expect(dayStamp(at(6), NOW)).toBe('thursday')
	})

	it('falls back to a short date once a weekday would repeat', () => {
		const stamp = dayStamp(at(7), NOW)
		expect(stamp).not.toBe('wednesday')
		expect(stamp).toMatch(/26|aug/)
		// still lowercase, like everything else the app writes
		expect(stamp).toBe(stamp.toLowerCase())
	})

	it('carries the year when the date is not from this one', () => {
		expect(dayStamp(new Date(2025, 2, 3, 9, 0), NOW)).toContain('2025')
	})

	it('crosses a day boundary on the calendar day, not on 24 hours', () => {
		// 23:50 yesterday is 40 minutes ago at 00:30, and still "yesterday"
		const justAfterMidnight = new Date(2026, 8, 2, 0, 30)
		expect(dayStamp(new Date(2026, 8, 1, 23, 50), justAfterMidnight)).toBe('yesterday')
	})
})

describe('formatTimeHeader', () => {
	it('is the day, then the time it happened at', () => {
		const moment = at(1, 14, 22)
		expect(formatTimeHeader(moment, NOW)).toBe(`yesterday ${clockTime(moment)}`)
	})

	it('splits into segments with the day carrying the weight', () => {
		const moment = at(0, 9, 5)
		expect(timeHeaderSegments(moment, NOW)).toEqual([
			{ text: 'today', strong: true },
			{ text: ` ${clockTime(moment)}` },
		])
	})
})

describe('needsTimeHeader', () => {
	const base = new Date(2026, 8, 2, 12, 0)

	it('marks a silence at or past the gap', () => {
		expect(needsTimeHeader(base, new Date(base.getTime() + TIME_HEADER_GAP_MS))).toBe(true)
		expect(needsTimeHeader(base, new Date(base.getTime() + 3 * TIME_HEADER_GAP_MS))).toBe(true)
	})

	it('leaves a conversation that kept going alone', () => {
		expect(needsTimeHeader(base, new Date(base.getTime() + 59 * 60 * 1000))).toBe(false)
	})

	it('marks a day boundary, which is only ever a long silence', () => {
		expect(needsTimeHeader(base, new Date(2026, 8, 3, 9, 0))).toBe(true)
	})

	it('has nothing to mark before the first message', () => {
		expect(needsTimeHeader(null, base)).toBe(false)
	})

	it('never marks a moment that went backwards', () => {
		expect(needsTimeHeader(base, new Date(base.getTime() - 5 * TIME_HEADER_GAP_MS))).toBe(false)
	})
})

describe('receiptStamp', () => {
	const sentAt = new Date(2026, 8, 2, 12, 0)

	it('stays bare when the read followed the message closely', () => {
		expect(receiptStamp(new Date(sentAt.getTime() + 60_000), sentAt, NOW)).toBe('')
	})

	it('names the clock alone when the read came later the same day', () => {
		const readAt = new Date(sentAt.getTime() + 3 * RECEIPT_STAMP_GAP_MS)
		expect(receiptStamp(readAt, sentAt, NOW)).toBe(clockTime(readAt))
	})

	it('names the day too once the read is older than today', () => {
		const olderSend = new Date(2026, 8, 1, 9, 0)
		const readAt = new Date(2026, 8, 1, 20, 15)
		expect(receiptStamp(readAt, olderSend, NOW)).toBe(`yesterday ${clockTime(readAt)}`)
	})

	it('never invents a time it was not told', () => {
		expect(receiptStamp(null, sentAt, NOW)).toBe('')
		expect(receiptStamp(new Date(), null, NOW)).toBe('')
	})
})
