/**
 * the times the transcript itself shows: the quiet headers between messages,
 * and the time a read receipt carries.
 *
 * imessage does not date every bubble. it drops a centered stamp whenever
 * ENOUGH TIME has passed since the last one - a day boundary is just the most
 * visible case of that - and it grades the wording by how old the moment is.
 * both rules live here so a header and a receipt never disagree about what
 * "yesterday" means.
 *
 * `Timestamp.svelte` stays the app's prose date ("yesterday at 2:22 pm"); these
 * are the transcript's compact forms, which drop the preposition and stay
 * lowercase.
 */

import type { SystemRowSegment } from './systemEvents'

/**
 * the silence a stamp needs before it earns a header.
 *
 * imessage's own gap: long enough that a conversation reads as one stretch,
 * short enough that picking a chat back up after lunch is dated.
 */
export const TIME_HEADER_GAP_MS = 60 * 60 * 1000

/**
 * how long after a message a read still counts as immediate.
 *
 * under this the receipt is the bare word - "read" right under a message you
 * just sent needs no clock. the same gap as a header, so the two surfaces treat
 * "a while later" identically.
 */
export const RECEIPT_STAMP_GAP_MS = TIME_HEADER_GAP_MS

function startOfDay(date: Date): Date {
	return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

/** the clock part, in the reader's own locale and hour cycle. */
export function clockTime(date: Date): string {
	return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }).toLowerCase()
}

/**
 * how a day is named, graduated by age: today, yesterday, the weekday while it
 * is still unambiguous, and a short date once it is not. a date from another
 * year carries the year, since the weekday-and-month form would not place it.
 */
export function dayStamp(date: Date, now: Date = new Date()): string {
	const dayDiff = Math.floor(
		(startOfDay(now).getTime() - startOfDay(date).getTime()) / 86_400_000
	)
	if (dayDiff === 0) return 'today'
	if (dayDiff === 1) return 'yesterday'
	if (dayDiff > 1 && dayDiff < 7) {
		return date.toLocaleDateString([], { weekday: 'long' }).toLowerCase()
	}
	const sameYear = date.getFullYear() === now.getFullYear()
	return date
		.toLocaleDateString([], {
			month: 'short',
			day: 'numeric',
			year: sameYear ? undefined : 'numeric',
		})
		.toLowerCase()
}

/** the header's full text: the day, then the time it happened at. */
export function formatTimeHeader(date: Date, now: Date = new Date()): string {
	return `${dayStamp(date, now)} ${clockTime(date)}`
}

/** the header as row copy, with the day carrying the weight. */
export function timeHeaderSegments(date: Date, now: Date = new Date()): SystemRowSegment[] {
	return [{ text: dayStamp(date, now), strong: true }, { text: ` ${clockTime(date)}` }]
}

/**
 * whether a gap earns a header.
 *
 * a header marks a SILENCE, so there is none to mark before the first thing in
 * the transcript - dating the top of it is the caller's business, since only
 * the caller knows whether that top is the beginning of the chat or just as far
 * back as it has paged.
 */
export function needsTimeHeader(previous: Date | null, at: Date): boolean {
	if (!previous) return false
	return at.getTime() - previous.getTime() >= TIME_HEADER_GAP_MS
}

/**
 * the time a receipt names, or '' when it should stay a bare word.
 *
 * a read that followed the message closely says nothing worth a clock; one that
 * came hours or days later is the interesting part of the receipt. an unknown
 * read time is never guessed - the cursor fanout carries none, so a cold-opened
 * thread renders the word alone.
 */
export function receiptStamp(
	readAt: Date | null,
	messageAt: Date | null,
	now: Date = new Date()
): string {
	if (!readAt) return ''
	if (!messageAt) return ''
	if (readAt.getTime() - messageAt.getTime() < RECEIPT_STAMP_GAP_MS) return ''
	const day = dayStamp(readAt, now)
	return day === 'today' ? clockTime(readAt) : `${day} ${clockTime(readAt)}`
}
